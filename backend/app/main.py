import json
import logging
import secrets
import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import FastAPI, Depends, HTTPException, Request, Response, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, delete, or_, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from .config import settings
from .db import get_db
from .models import User, Session, PasswordReset, Category, Ticket, Message, TicketHistory, AuditEvent, utcnow
from .schemas import (Login, TicketCreate, TicketPatch, MessageCreate, ProfilePatch,
                      PasswordChange, UserState, ResetRequest, ResetComplete)
from .security import hasher, verify, digest, DUMMY_HASH

cfg = settings()
app = FastAPI(title='SupportDesk', version='1.0.0', docs_url='/docs' if cfg.app_env != 'production' else None,
              redoc_url=None, openapi_url='/openapi.json' if cfg.app_env != 'production' else None)
app.add_middleware(CORSMiddleware, allow_origins=cfg.origins, allow_credentials=True,
                   allow_methods=['GET', 'POST', 'PATCH'], allow_headers=['Content-Type', 'X-CSRF-Token'])
logger = logging.getLogger('supportdesk.audit')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
logger.propagate = False
DB = Annotated[DBSession, Depends(get_db)]


def public_user(user):
    return {'id': user.id, 'name': user.name, 'email': user.email, 'role': user.role, 'active': user.active}


def audit(db, request, event, user=None, result='success', resource=None, details=None):
    allowed_details = {k: v for k, v in (details or {}).items() if k in {'fields', 'account_key', 'source'}}
    item = {'timestamp': utcnow().isoformat(), 'event': event, 'user_id': user.id if user else None,
            'role': user.role if user else None, 'result': result, 'request_id': request.state.request_id,
            'resource': resource, 'demo': False, 'details': allowed_details}
    db.add(AuditEvent(**{k: v for k, v in item.items() if k != 'timestamp'}))
    logger.info(json.dumps(item, ensure_ascii=False))


@app.middleware('http')
async def guard(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') not in cfg.origins:
            return JSONResponse({'detail': 'Origine non autorisée.'}, status_code=403)
    try:
        response = await call_next(request)
    except SQLAlchemyError:
        response = JSONResponse({'detail': 'Service temporairement indisponible.'}, status_code=503)
    response.headers['X-Request-ID'] = request.state.request_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Never echo input values (password/token/body) in validation errors.
    return JSONResponse({'detail': 'Données invalides. Vérifiez les champs du formulaire.',
                         'fields': [str(e['loc'][-1]) for e in exc.errors()]}, status_code=422)


def denied(db, request, user, resource):
    audit(db, request, 'ACCESS_DENIED', user, 'denied', resource)
    db.commit()
    raise HTTPException(403, 'Accès refusé.')


def authenticated(request: Request, db: DB):
    token = request.cookies.get('sd_session', '')
    session = db.scalar(select(Session).where(Session.token_hash == digest(token), Session.expires_at > utcnow())) if token else None
    user = db.get(User, session.user_id) if session else None
    if not user or not user.active:
        raise HTTPException(401, 'Session expirée. Veuillez vous reconnecter.')
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        csrf = request.headers.get('x-csrf-token', '')
        if not csrf or not secrets.compare_digest(session.csrf_hash, digest(csrf)):
            denied(db, request, user, 'csrf')
    return user


Current = Annotated[User, Depends(authenticated)]


def administrator(request: Request, db: DB, user: Current):
    if user.role != 'admin':
        denied(db, request, user, 'admin')
    return user


Admin = Annotated[User, Depends(administrator)]


def ticket_access(db, request, user, ticket_id):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(404, 'Ticket introuvable.')
    if user.role != 'admin' and ticket.requester_id != user.id:
        denied(db, request, user, f'ticket:{ticket_id}')
    return ticket


def ticket_view(db, ticket):
    category = db.get(Category, ticket.category_id)
    requester = db.get(User, ticket.requester_id)
    assignee = db.get(User, ticket.assignee_id) if ticket.assignee_id else None
    return {'id': ticket.id, 'reference': f'SUP-{ticket.id + 1000}', 'title': ticket.title,
            'description': ticket.description, 'category_id': ticket.category_id, 'category': category.name,
            'priority': ticket.priority, 'status': ticket.status, 'requester': public_user(requester),
            'assignee': public_user(assignee) if assignee else None,
            'created_at': ticket.created_at, 'updated_at': ticket.updated_at}


def revoke_sessions(db, user_id):
    db.execute(delete(Session).where(Session.user_id == user_id))
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user_id))


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/ready')
def ready(db: DB):
    try:
        db.execute(text('SELECT 1 FROM sd_users LIMIT 1'))
    except SQLAlchemyError:
        raise HTTPException(503, 'Base ou migrations indisponibles.') from None
    return {'status': 'ready'}


@app.get('/api/config')
def configuration():
    return {'reset_mode': cfg.reset_mode if cfg.app_env != 'production' else 'disabled',
            'attachments_enabled': False, 'email_enabled': False}


@app.post('/api/auth/login')
def login(data: Login, request: Request, response: Response, db: DB):
    email = str(data.email).lower().strip()
    account_key = digest(email)
    cutoff = utcnow() - timedelta(minutes=15)
    recent = list(db.scalars(select(AuditEvent).where(AuditEvent.event == 'LOGIN_FAILED', AuditEvent.timestamp > cutoff)))
    if sum(e.details.get('account_key') == account_key for e in recent) >= 8:
        raise HTTPException(429, 'Trop de tentatives. Réessayez dans 15 minutes.')
    user = db.scalar(select(User).where(User.email == email))
    valid = verify(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.active:
        audit(db, request, 'LOGIN_FAILED', result='failure', details={'account_key': account_key})
        db.commit()
        raise HTTPException(401, 'Adresse e-mail ou mot de passe incorrect.')
    db.execute(delete(Session).where(Session.expires_at <= utcnow()))
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(Session(token_hash=digest(token), csrf_hash=digest(csrf), user_id=user.id,
                   expires_at=utcnow() + timedelta(hours=cfg.session_hours)))
    audit(db, request, 'LOGIN_SUCCESS', user)
    db.commit()
    response.set_cookie('sd_session', token, httponly=True, secure=cfg.cookie_secure, samesite='lax',
                        max_age=cfg.session_hours * 3600, path='/')
    response.set_cookie('sd_csrf', csrf, httponly=False, secure=cfg.cookie_secure, samesite='lax',
                        max_age=cfg.session_hours * 3600, path='/')
    return public_user(user)


@app.post('/api/auth/logout')
def logout(request: Request, response: Response, db: DB, user: Current):
    db.execute(delete(Session).where(Session.token_hash == digest(request.cookies.get('sd_session', ''))))
    audit(db, request, 'LOGOUT', user)
    db.commit()
    response.delete_cookie('sd_session', path='/')
    response.delete_cookie('sd_csrf', path='/')
    return {'message': 'Déconnexion effectuée.'}


@app.get('/api/auth/me')
def me(user: Current):
    return public_user(user)


@app.patch('/api/profile')
def profile(data: ProfilePatch, request: Request, db: DB, user: Current):
    user.name = data.name
    audit(db, request, 'PROFILE_UPDATED', user, resource=f'user:{user.id}')
    db.commit()
    return public_user(user)


@app.post('/api/auth/password')
def change_password(data: PasswordChange, request: Request, response: Response, db: DB, user: Current):
    if not verify(data.current_password, user.password_hash):
        raise HTTPException(400, 'Mot de passe actuel incorrect.')
    user.password_hash = hasher.hash(data.new_password)
    revoke_sessions(db, user.id)
    audit(db, request, 'PASSWORD_CHANGED', user)
    db.commit()
    response.delete_cookie('sd_session', path='/')
    response.delete_cookie('sd_csrf', path='/')
    return {'message': 'Mot de passe modifié. Reconnectez-vous.'}


@app.post('/api/auth/forgot-password')
def forgot(data: ResetRequest):
    # No fake SMTP success, no reset token exposed to unauthenticated callers.
    return {'mode': cfg.reset_mode, 'message': 'Aucun e-mail envoyé. Contactez votre administrateur.' +
            (' Un lien de démonstration peut être généré depuis la gestion des utilisateurs.' if cfg.reset_mode == 'demo' else '')}


@app.post('/api/admin/users/{user_id}/reset-link')
def demo_reset(user_id: int, request: Request, db: DB, admin: Admin):
    if cfg.app_env == 'production' or cfg.reset_mode != 'demo':
        raise HTTPException(409, 'Réinitialisation de démonstration désactivée.')
    user = db.get(User, user_id)
    if not user or not user.active or not user.demo_key:
        raise HTTPException(400, 'Compte de démonstration actif requis.')
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    token = secrets.token_urlsafe(32)
    db.add(PasswordReset(token_hash=digest(token), user_id=user.id, expires_at=utcnow() + timedelta(minutes=15)))
    audit(db, request, 'PASSWORD_RESET_REQUESTED', admin, resource=f'user:{user.id}')
    db.commit()
    return {'path': '/reset-password#token=' + token, 'message': 'Mode démonstration : aucun e-mail envoyé. Lien valable 15 minutes.'}


@app.post('/api/auth/reset-password')
def reset_password(data: ResetComplete, request: Request, db: DB):
    reset = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == digest(data.token)).with_for_update())
    if not reset or reset.expires_at <= utcnow():
        raise HTTPException(400, 'Lien invalide ou expiré.')
    user = db.get(User, reset.user_id)
    if not user.active:
        raise HTTPException(400, 'Lien invalide ou expiré.')
    user.password_hash = hasher.hash(data.new_password)
    revoke_sessions(db, user.id)
    audit(db, request, 'PASSWORD_RESET_COMPLETED', user)
    db.commit()
    return {'message': 'Mot de passe modifié. Vous pouvez vous connecter.'}


@app.get('/api/categories')
def categories(db: DB, user: Current):
    return [{'id': c.id, 'name': c.name} for c in db.scalars(select(Category).order_by(Category.id))]


def scoped_tickets(user):
    return select(Ticket) if user.role == 'admin' else select(Ticket).where(Ticket.requester_id == user.id)


@app.get('/api/tickets')
def tickets(db: DB, user: Current, q: str = Query('', max_length=160), status: str = '', priority: str = '',
            category_id: int | None = None, assignee_id: int | None = None,
            page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=100)):
    stmt = scoped_tickets(user)
    if q:
        term = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        conditions = [Ticket.title.ilike(term, escape='\\'), Ticket.description.ilike(term, escape='\\')]
        reference = q.upper().removeprefix('SUP-')
        if reference.isdigit():
            conditions.append(Ticket.id == int(reference) - 1000)
        stmt = stmt.where(or_(*conditions))
    for field, value in [(Ticket.status, status), (Ticket.priority, priority), (Ticket.category_id, category_id), (Ticket.assignee_id, assignee_id)]:
        if value:
            stmt = stmt.where(field == value)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(Ticket.updated_at.desc(), Ticket.id.desc()).offset((page - 1) * page_size).limit(page_size))
    return {'items': [ticket_view(db, t) for t in items], 'total': total, 'page': page, 'page_size': page_size}


@app.get('/api/dashboard')
def dashboard(db: DB, user: Current):
    rows = list(db.scalars(scoped_tickets(user)))
    statuses = {s: sum(t.status == s for t in rows) for s in ['Nouveau', 'En cours', 'En attente', 'Résolu']}
    recent = sorted(rows, key=lambda t: (t.updated_at, t.id), reverse=True)[:5]
    urgent = sorted([t for t in rows if t.priority == 'Haute' and t.status != 'Résolu'], key=lambda t: t.created_at)[:5]
    return {'total': len(rows), 'statuses': statuses, 'recent': [ticket_view(db, t) for t in recent],
            'urgent': [ticket_view(db, t) for t in urgent]}


@app.post('/api/tickets', status_code=201)
def create_ticket(data: TicketCreate, request: Request, db: DB, user: Current):
    if not db.get(Category, data.category_id):
        raise HTTPException(422, 'Catégorie inconnue.')
    ticket = Ticket(**data.model_dump(), requester_id=user.id)
    db.add(ticket)
    db.flush()
    db.add(TicketHistory(ticket_id=ticket.id, actor_id=user.id, field='creation', new_value='Nouveau'))
    audit(db, request, 'TICKET_CREATED', user, resource=f'ticket:{ticket.id}')
    db.commit()
    return ticket_view(db, ticket)


@app.get('/api/tickets/{ticket_id}')
def detail(ticket_id: int, request: Request, db: DB, user: Current):
    ticket = ticket_access(db, request, user, ticket_id)
    result = ticket_view(db, ticket)
    messages = select(Message).where(Message.ticket_id == ticket_id)
    if user.role != 'admin':
        messages = messages.where(Message.internal.is_(False))
    result['messages'] = [{'id': m.id, 'body': m.body, 'internal': m.internal,
                           'author': public_user(db.get(User, m.author_id)), 'created_at': m.created_at}
                          for m in db.scalars(messages.order_by(Message.created_at, Message.id))]
    result['history'] = [{'id': h.id, 'field': h.field, 'old_value': h.old_value, 'new_value': h.new_value,
                          'actor': db.get(User, h.actor_id).name, 'created_at': h.created_at}
                         for h in db.scalars(select(TicketHistory).where(TicketHistory.ticket_id == ticket_id).order_by(TicketHistory.created_at.desc()))]
    return result


@app.post('/api/tickets/{ticket_id}/messages', status_code=201)
def add_message(ticket_id: int, data: MessageCreate, request: Request, db: DB, user: Current):
    ticket = ticket_access(db, request, user, ticket_id)
    if data.internal and user.role != 'admin':
        denied(db, request, user, f'ticket:{ticket_id}:internal')
    db.add(Message(ticket_id=ticket_id, author_id=user.id, **data.model_dump()))
    ticket.updated_at = utcnow()
    audit(db, request, 'TICKET_UPDATED', user, resource=f'ticket:{ticket_id}', details={'fields': ['internal_note' if data.internal else 'message']})
    db.commit()
    return {'message': 'Note interne ajoutée.' if data.internal else 'Réponse envoyée.'}


@app.patch('/api/admin/tickets/{ticket_id}')
def update_ticket(ticket_id: int, data: TicketPatch, request: Request, db: DB, admin: Admin):
    ticket = ticket_access(db, request, admin, ticket_id)
    changes = data.model_dump(exclude_unset=True)
    if ('status' in changes and changes['status'] is None) or ('priority' in changes and changes['priority'] is None):
        raise HTTPException(422, 'Statut et priorité ne peuvent pas être vides.')
    if data.assignee_id is not None:
        assignee = db.get(User, data.assignee_id)
        if not assignee or assignee.role != 'admin' or not assignee.active:
            raise HTTPException(422, 'Administrateur actif requis.')
    if data.status == 'Résolu' and ticket.status != 'Résolu' and not data.resolution:
        raise HTTPException(422, 'Un résumé de résolution est requis.')
    fields = []
    for field in ('status', 'priority', 'assignee_id'):
        if field in changes and getattr(ticket, field) != changes[field]:
            before = getattr(ticket, field)
            setattr(ticket, field, changes[field])
            old, new = str(before or 'Non affecté'), str(changes[field] or 'Non affecté')
            if field == 'assignee_id':
                old = db.get(User, before).name if before else 'Non affecté'
                new = db.get(User, changes[field]).name if changes[field] else 'Non affecté'
            db.add(TicketHistory(ticket_id=ticket_id, actor_id=admin.id, field=field, old_value=old, new_value=new))
            fields.append(field)
    if data.resolution:
        db.add(Message(ticket_id=ticket_id, author_id=admin.id, body='Résolution : ' + data.resolution, internal=False))
    if fields or data.resolution:
        ticket.updated_at = utcnow()
        audit(db, request, 'TICKET_UPDATED', admin, resource=f'ticket:{ticket_id}', details={'fields': fields})
        if 'assignee_id' in fields:
            audit(db, request, 'TICKET_ASSIGNED', admin, resource=f'ticket:{ticket_id}')
        if 'status' in fields and data.status == 'Résolu':
            audit(db, request, 'TICKET_RESOLVED', admin, resource=f'ticket:{ticket_id}')
    db.commit()
    return ticket_view(db, ticket)


@app.get('/api/admin/users')
def users(db: DB, admin: Admin):
    return [public_user(u) for u in db.scalars(select(User).order_by(User.name))]


@app.patch('/api/admin/users/{user_id}')
def user_state(user_id: int, data: UserState, request: Request, db: DB, admin: Admin):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, 'Compte introuvable.')
    if user.id == admin.id and not data.active:
        raise HTTPException(409, 'Vous ne pouvez pas désactiver votre propre compte.')
    user.active = data.active
    if not data.active:
        revoke_sessions(db, user.id)
    audit(db, request, 'USER_ENABLED' if data.active else 'USER_DISABLED', admin, resource=f'user:{user_id}')
    db.commit()
    return public_user(user)
