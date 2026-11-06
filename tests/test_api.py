from datetime import timedelta
from sqlalchemy import select, func
from app.models import User, Ticket, Message, TicketHistory, AuditEvent, Session, PasswordReset, Category, utcnow
from app.security import verify
from database.seed import seed
from conftest import login


def test_seed_idempotent_and_preserves_changes(db):
    counts = lambda: [db.scalar(select(func.count()).select_from(m)) for m in [User, Ticket, Message, TicketHistory, AuditEvent]]
    before = counts()
    assert before[0:2] == [10, 30]
    first = db.scalar(select(Ticket).order_by(Ticket.id))
    first.title = 'Titre modifié à conserver'
    db.commit()
    seed(db)
    assert counts() == before
    assert db.get(Ticket, first.id).title == 'Titre modifié à conserver'
    assert db.scalar(select(func.count()).select_from(User).where(User.role == 'admin')) == 2
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.demo.is_(True))) == 30


def test_seed_hashes_and_statuses(db):
    assert all(u.password_hash.startswith('$argon2id$') for u in db.scalars(select(User)))
    assert len(set(db.scalars(select(Ticket.status)))) == 4
    assert len(set(db.scalars(select(Category.name)))) == 7


def test_health_and_ready(client):
    assert client.get('/health').status_code == 200
    assert client.get('/ready').json()['status'] == 'ready'


def test_login_failure_cookie_and_logout(client, db):
    assert client.post('/api/auth/login', json={'email':'nobody@example.org','password':'wrong'}).status_code == 401
    user = login(client)
    assert 'HttpOnly' in client.post('/api/auth/login', json={'email':user['email'],'password':__import__('app.config',fromlist=['settings']).settings().demo_password}).headers.get_list('set-cookie')[0]
    client.headers['X-CSRF-Token'] = client.cookies['sd_csrf']
    assert client.get('/api/auth/me').json()['id'] == user['id']
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/auth/me').status_code == 401


def test_permissions_and_internal_notes(client, db):
    user = login(client)
    assert client.get('/api/admin/users').status_code == 403
    other = db.scalar(select(Ticket).where(Ticket.requester_id != user['id']))
    assert client.get(f'/api/tickets/{other.id}').status_code == 403
    mine = db.scalar(select(Ticket).where(Ticket.requester_id == user['id'], Ticket.status != 'Nouveau'))
    assert db.scalar(select(Message).where(Message.ticket_id == mine.id, Message.internal.is_(True)))
    r = client.get(f'/api/tickets/{mine.id}')
    assert r.status_code == 200 and all(not m['internal'] for m in r.json()['messages'])
    assert client.post(f'/api/tickets/{mine.id}/messages', json={'body':'note interdite','internal':True}).status_code == 403
    assert client.patch(f'/api/admin/tickets/{mine.id}', json={'status':'En cours'}).status_code == 403


def test_csrf_and_origin(client, db):
    login(client)
    client.headers.pop('X-CSRF-Token')
    assert client.patch('/api/profile', json={'name':'Nom de test'}).status_code == 403
    assert client.post('/api/auth/login', headers={'Origin':'https://evil.example'}, json={'email':'a@example.org','password':'x'}).status_code == 403


def test_create_filter_and_conversation(client, db):
    user = login(client)
    cat = db.scalar(select(Category))
    r = client.post('/api/tickets', json={'title':'Problème réseau de test','description':'Connexion réseau indisponible depuis ce matin.','category_id':cat.id,'priority':'Haute'})
    assert r.status_code == 201
    ticket = r.json()
    assert ticket['requester']['id'] == user['id'] and ticket['status'] == 'Nouveau'
    found = client.get('/api/tickets', params={'q':ticket['reference'],'priority':'Haute'}).json()
    assert found['total'] == 1
    assert client.post(f"/api/tickets/{ticket['id']}/messages", json={'body':'Voici une précision.'}).status_code == 201
    assert client.get(f"/api/tickets/{ticket['id']}").json()['messages'][0]['body'] == 'Voici une précision.'


def test_admin_updates_resolution_and_audit(client, db):
    admin = login(client, True)
    t = db.scalar(select(Ticket).where(Ticket.status != 'Résolu'))
    assert client.patch(f'/api/admin/tickets/{t.id}', json={'status':'Résolu'}).status_code == 422
    r = client.patch(f'/api/admin/tickets/{t.id}', json={'status':'Résolu','priority':'Haute','assignee_id':admin['id'],'resolution':'Configuration corrigée et vérifiée.'})
    assert r.status_code == 200 and r.json()['status'] == 'Résolu'
    events = set(db.scalars(select(AuditEvent.event).where(AuditEvent.demo.is_(False))))
    assert {'TICKET_UPDATED','TICKET_RESOLVED','TICKET_ASSIGNED'} <= events


def test_disable_revokes_sessions(client, db):
    user = login(client)
    token = client.cookies['sd_session']
    login(client, True)
    assert client.patch(f"/api/admin/users/{user['id']}", json={'active':False}).status_code == 200
    client.cookies.set('sd_session', token)
    assert client.get('/api/auth/me').status_code == 401


def test_dashboard_matches_db(client, db):
    user = login(client)
    d = client.get('/api/dashboard').json()
    assert d['total'] == db.scalar(select(func.count()).select_from(Ticket).where(Ticket.requester_id == user['id']))
    assert sum(d['statuses'].values()) == d['total']


def test_password_change_invalidates_session(client, db):
    from app.config import settings
    user = login(client)
    assert client.post('/api/auth/password', json={'current_password':settings().demo_password,'new_password':'New-test-only-password-2026'}).status_code == 200
    assert client.get('/api/auth/me').status_code == 401
    assert verify('New-test-only-password-2026', db.get(User,user['id']).password_hash)


def test_demo_reset_single_use_and_no_fake_email(client, db):
    assert 'Aucun e-mail envoyé' in client.post('/api/auth/forgot-password', json={'email':'a@example.org'}).json()['message']
    admin = login(client,True)
    result = client.post(f"/api/admin/users/{admin['id']}/reset-link").json()
    token = result['path'].split('token=')[1]
    assert db.scalar(select(PasswordReset)).token_hash != token
    payload = {'token':token,'new_password':'Another-test-password-2026'}
    assert client.post('/api/auth/reset-password', json=payload).status_code == 200
    assert client.post('/api/auth/reset-password', json=payload).status_code == 400


def test_expired_session_and_validation_redaction(client, db):
    login(client)
    session = db.scalar(select(Session))
    session.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get('/api/auth/me').status_code == 401
    secret = 'DO-NOT-ECHO-THIS-SECRET'
    r = client.post('/api/auth/login', json={'email':secret,'password':secret})
    assert r.status_code == 422 and secret not in r.text


def test_sql_search_literal_and_unknown_category(client, db):
    login(client)
    assert client.get('/api/tickets', params={'q':"%' OR 1=1 --"}).json()['total'] == 0
    assert client.post('/api/tickets', json={'title':'Titre valide','description':'Une description complète.','category_id':999999}).status_code == 422


def test_rate_limit(client):
    for _ in range(8):
        assert client.post('/api/auth/login', json={'email':'limited@example.org','password':'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={'email':'limited@example.org','password':'wrong'}).status_code == 429


def test_audit_redaction(client, db, caplog):
    from app.config import settings
    import logging
    with caplog.at_level(logging.INFO,logger='supportdesk.audit'):
        login(client)
    serialized = str([(e.event,e.details,e.resource) for e in db.scalars(select(AuditEvent))])
    assert settings().demo_password not in serialized
    assert client.cookies['sd_session'] not in serialized
