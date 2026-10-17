"""Helpers de autorização dos testes (os mesmos nomes do Trino) e as regras
de acesso do núcleo: perfil, carteira de contratos e escrita x leitura."""
import json
import uuid


def _make_user(app_module, role='pleno', perms=(), client_ids=()):
    """Cria e persiste um usuário com perfil/permissões/contratos definidos."""
    from app import Client, User, db
    u = User(name='Teste', email=f'{uuid.uuid4().hex[:8]}@t.com', role=role,
             permissions_json=json.dumps(list(perms)), must_change_password=False)
    u.set_password('senha12345')
    for cid in client_ids:
        c = db.session.get(Client, cid)
        if c:
            u.clients.append(c)
    db.session.add(u)
    db.session.commit()
    return u.id, u.email


def _login(client, email):
    return client.post('/login', data={'email': email, 'password': 'senha12345'})


def _cleanup_users(app_module, *emails):
    from app import User, db
    for e in emails:
        u = User.query.filter_by(email=e).first()
        if u:
            u.clients = []
            db.session.delete(u)
    db.session.commit()
