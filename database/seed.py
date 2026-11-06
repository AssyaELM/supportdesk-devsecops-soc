"""Explicit, non-destructive demo seed. Run from project root with PYTHONPATH=backend."""
from datetime import timedelta
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.config import settings
from app.db import engine
from app.models import User, Category, Ticket, Message, TicketHistory, AuditEvent, utcnow
from app.security import hasher

CATEGORIES = ['Matériel', 'Logiciels', 'Réseau', 'VPN', 'Comptes', 'Impression', 'Messagerie']
PEOPLE = [('Assia Benkacem', 'assia.benkacem'), ('Claire Martin', 'claire.martin'),
          ('Sophie Lambert', 'sophie.lambert'), ('Thomas Bernard', 'thomas.bernard'),
          ('Paul Renard', 'paul.renard'), ('Julie Petit', 'julie.petit'),
          ('Marc Girard', 'marc.girard'), ('Lina Moreau', 'lina.moreau'),
          ('Youssef Amrani', 'youssef.amrani'), ('Élodie Garnier', 'elodie.garnier')]
CASES = [
    ('Accès VPN impossible', 'VPN', 'La connexion VPN échoue depuis ce matin malgré plusieurs essais depuis mon domicile.'),
    ('Clavier qui ne répond plus', 'Matériel', 'Plusieurs touches du clavier ne répondent plus. Un redémarrage ne résout pas le problème.'),
    ('Imprimante du troisième étage indisponible', 'Impression', 'Les documents restent dans la file d’attente et aucune page ne sort de l’imprimante.'),
    ('Installation d’un logiciel de visioconférence', 'Logiciels', 'Je souhaite installer le logiciel approuvé pour participer aux réunions de mon équipe.'),
    ('Compte professionnel bloqué', 'Comptes', 'Mon compte affiche un message de blocage et je ne peux plus ouvrir ma session de travail.'),
    ('Connexion réseau intermittente', 'Réseau', 'La connexion réseau se coupe plusieurs fois par heure dans notre bureau.'),
    ('Messages sortants en attente', 'Messagerie', 'Mes courriels restent dans la boîte d’envoi alors que la connexion Internet fonctionne.'),
    ('Écran externe non détecté', 'Matériel', 'L’écran externe reste noir après le branchement de la station d’accueil.'),
    ('Mise à jour du logiciel métier', 'Logiciels', 'L’application indique qu’une version plus récente est nécessaire pour ouvrir les dossiers.'),
    ('Accès au dossier partagé refusé', 'Comptes', 'Je ne peux plus accéder au dossier partagé de mon équipe depuis mon changement de poste.'),
    ('VPN déconnecté après quelques minutes', 'VPN', 'La session distante se ferme au bout de cinq minutes lors de mes déplacements.'),
    ('Impression recto verso impossible', 'Impression', 'L’option recto verso n’est plus disponible sur l’imprimante du service.'),
    ('Wi-Fi de la salle de réunion lent', 'Réseau', 'Le Wi-Fi de la salle de réunion ralentit fortement pendant les appels vidéo.'),
    ('Calendrier partagé absent', 'Messagerie', 'Le calendrier de mon équipe n’apparaît plus dans mon application de messagerie.'),
    ('Batterie du portable défectueuse', 'Matériel', 'L’ordinateur s’éteint dès que je retire le chargeur, même après une nuit de charge.'),
]


def seed(db: Session):
    cfg = settings()
    if cfg.app_env == 'production' or not cfg.demo_seed_enabled:
        raise RuntimeError('Peuplement interdit : activer DEMO_SEED_ENABLED uniquement en développement.')
    if len(cfg.demo_password) < 12:
        raise RuntimeError('DEMO_PASSWORD doit contenir au moins 12 caractères.')
    if cfg.demo_user_email.lower() == cfg.demo_admin_email.lower():
        raise RuntimeError('Les adresses de démonstration doivent être distinctes.')
    # Serialize concurrent seeds; never delete or replace existing rows.
    db.execute(text('SELECT pg_advisory_xact_lock(73829401)'))
    categories = {}
    for name in CATEGORIES:
        row = db.scalar(select(Category).where(Category.name == name))
        if not row:
            row = Category(name=name)
            db.add(row)
            db.flush()
        categories[name] = row
    people = []
    for index, (name, slug) in enumerate(PEOPLE):
        key = f'supportdesk-demo-user-{index}'
        email = cfg.demo_user_email.lower() if index == 0 else cfg.demo_admin_email.lower() if index == 8 else slug + '@example.org'
        user = db.scalar(select(User).where(User.demo_key == key))
        if not user:
            if db.scalar(select(User).where(User.email == email)):
                raise RuntimeError('Une adresse de démonstration existe déjà hors de ce peuplement. Aucune donnée écrasée.')
            user = User(name=name, email=email, role='admin' if index >= 8 else 'user', active=True,
                        password_hash=hasher.hash(cfg.demo_password), demo_key=key)
            db.add(user)
            db.flush()
        people.append(user)
    now = utcnow()
    for index in range(30):
        key = f'supportdesk-demo-ticket-{index}'
        if db.scalar(select(Ticket).where(Ticket.demo_key == key)):
            continue
        title, category, description = CASES[index % len(CASES)]
        requester = people[index % 8]
        admin = people[8 + index % 2]
        status = ['Nouveau', 'En cours', 'En attente', 'Résolu'][(index // 3 + index) % 4]
        # Ensure the first demo user has all four statuses, not just a single state.
        status = ['Nouveau', 'En cours', 'En attente', 'Résolu'][(index // 8 + index) % 4]
        created = now - timedelta(days=30 - index, hours=index % 5)
        ticket = Ticket(title=title, description=description, category_id=categories[category].id,
                        priority=['Haute', 'Moyenne', 'Basse'][index % 3], status=status,
                        requester_id=requester.id, assignee_id=admin.id if status != 'Nouveau' else None,
                        demo_key=key, created_at=created, updated_at=created + timedelta(hours=2))
        db.add(ticket)
        db.flush()
        db.add(Message(ticket_id=ticket.id, author_id=requester.id, body=description, internal=False, created_at=created))
        db.add(TicketHistory(ticket_id=ticket.id, actor_id=requester.id, field='creation', new_value='Nouveau', created_at=created))
        if status != 'Nouveau':
            db.add(Message(ticket_id=ticket.id, author_id=admin.id, internal=False,
                           body='Bonjour, votre demande a été prise en charge. Nous vérifions la configuration et vous tenons informé.', created_at=created + timedelta(minutes=30)))
            db.add(Message(ticket_id=ticket.id, author_id=admin.id, internal=True,
                           body='Donnée fictive : diagnostic initial effectué, vérification de la configuration du poste à poursuivre.', created_at=created + timedelta(minutes=45)))
            db.add(TicketHistory(ticket_id=ticket.id, actor_id=admin.id, field='status', old_value='Nouveau', new_value='En cours', created_at=created + timedelta(minutes=30)))
            if status in {'En attente', 'Résolu'}:
                db.add(TicketHistory(ticket_id=ticket.id, actor_id=admin.id, field='status', old_value='En cours', new_value=status, created_at=created + timedelta(hours=2)))
            if status == 'Résolu':
                db.add(Message(ticket_id=ticket.id, author_id=admin.id, body='Résolution : configuration corrigée et fonctionnement vérifié avec le demandeur (démonstration).', internal=False, created_at=created + timedelta(hours=2)))
        db.add(AuditEvent(event='TICKET_CREATED', user_id=requester.id, role='user', result='success',
                          request_id=f'demo-seed-{index}', resource=f'ticket:{ticket.id}', demo=True,
                          timestamp=created, details={'source': 'demo_seed'}))
    db.commit()


if __name__ == '__main__':
    with Session(engine()) as db:
        seed(db)
    print('Peuplement terminé : données de démonstration ajoutées sans remplacement des données existantes.')
