"""O núcleo: quem entra (User), em que contrato (Client) e os avisos.

Os nomes internos são os mesmos do Trino Intelligence, de onde a Passagem de
Turno veio: ``User.name``, ``Client.cost_center``, ``client_id`` nas tabelas
do módulo, os perfis ``master``/``pleno``/``encarregado``. Não é preguiça de
traduzir — é o que permite trazer o módulo e os seus testes quase sem
alteração, e com eles as regras que custaram para acertar (contagem por área,
rascunho fora dos indicadores, tarefa sem resposta...). Na TELA tudo fala a
língua do Facilities: "contrato", "gestor", "técnico".

Perfis (``role``) e o que cada um faz:

* ``master``       — Administrador: tudo, todos os contratos, cadastros.
* ``pleno``        — Gestor: os contratos dele; configura a passagem, pede
                     tarefas, acompanha painel e relatório, gerencia chamados.
* ``encarregado``  — Encarregado do posto (limpeza, portaria...): faz a
                     passagem de turno e abre chamados. Nada de cadastro.
* ``tecnico``      — Técnico de manutenção: atende os chamados e também faz
                     a passagem de turno da equipe dele.
* ``visualizador`` — Diretoria: lê tudo, não altera nada.
"""
import json
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from facilities.extensions import db

PERFIS = {
    'master': 'Administrador',
    'pleno': 'Gestor',
    'encarregado': 'Encarregado',
    'tecnico': 'Técnico de manutenção',
    'visualizador': 'Diretoria (só leitura)',
}

# Os módulos com tela. O nome da passagem é o mesmo do Trino
# (``diario_operacional``) pelo motivo do topo deste arquivo.
MODULO_PASSAGEM = 'diario_operacional'
MODULO_CHAMADOS = 'chamados'
MODULES = [MODULO_PASSAGEM, MODULO_CHAMADOS]

# Quem AGE em cada módulo, por perfil. O perfil decide sozinho — não há
# caixinha de módulo no cadastro: um clique errado não abre nada a ninguém.
MODULOS_DO_PERFIL = {
    'pleno': (MODULO_PASSAGEM, MODULO_CHAMADOS),
    'encarregado': (MODULO_PASSAGEM, MODULO_CHAMADOS),
    'tecnico': (MODULO_PASSAGEM, MODULO_CHAMADOS),
    'visualizador': (),
}


user_clients = db.Table(
    'user_clients',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('client_id', db.Integer, db.ForeignKey('clients.id'), primary_key=True),
)


class Client(db.Model):
    """Um LOCAL da operação (na origem, o "contrato"): o armazém, a loja, a sede.

    O nome interno (``clients``, ``client_id``) vem do Trino e não muda. Desde
    a Fase 1 o local pertence a um cliente (``contratante_id``, ver
    ``facilities/cadastros/models.py``) e fica num estado; o ``cost_center``
    é o SUBCENTRO de custo do local (o centro pai é do cliente). Os dois
    campos são opcionais: local antigo, sem cliente, funciona como antes.
    """
    __tablename__ = 'clients'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    cost_center = db.Column(db.String(50))
    endereco = db.Column(db.String(255))
    responsible_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    contratante_id = db.Column(db.Integer,
                               db.ForeignKey('contratantes.id', ondelete='RESTRICT'),
                               nullable=True, index=True)
    estado_id = db.Column(db.Integer, db.ForeignKey('estados.id', ondelete='RESTRICT'),
                          nullable=True, index=True)

    responsavel = db.relationship('User', foreign_keys=[responsible_user_id])
    contratante = db.relationship('Contratante', backref='locais')
    estado = db.relationship('Estado')

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'cost_center': self.cost_center,
                'endereco': self.endereco, 'is_active': self.is_active,
                'responsible_user_id': self.responsible_user_id,
                'contratante_id': self.contratante_id, 'estado_id': self.estado_id}


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='encarregado', nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    # Permissões FINAS, concedidas pessoa a pessoa (lista de strings).
    permissions_json = db.Column(db.Text, default='[]')
    # Todos os contratos, inclusive os cadastrados depois (diretoria).
    all_clients = db.Column(db.Boolean, default=False, nullable=False)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)
    failed_login_count = db.Column(db.Integer, default=0, nullable=False)
    lockout_until = db.Column(db.DateTime, nullable=True)
    # Sobe a cada troca de senha/desativação: derruba as sessões abertas.
    session_epoch = db.Column(db.Integer, default=0, nullable=False)

    clients = db.relationship('Client', secondary=user_clients, backref='linked_users')

    MODULES = MODULES

    # Capacidades que não são módulo: dentro de um módulo que a pessoa já
    # abre, liberam uma ação reservada.
    PERMISSOES_FINAS = {
        'diario_config': ('Configurar o modelo de passagem de turno — '
                          'perguntas, turnos, áreas e tipos de ocorrência'),
    }

    # ── Senha ─────────────────────────────────────────────────────────
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        # A época da sessão vai junto: trocar a senha invalida o cookie antigo.
        return f'{self.id}:{self.session_epoch or 0}'

    # ── Perfil e acesso ───────────────────────────────────────────────
    def _effective_role(self):
        return self.role or 'encarregado'

    @property
    def perfil_rotulo(self):
        return PERFIS.get(self._effective_role(), self._effective_role())

    @property
    def client_ids(self):
        return [c.id for c in self.clients]

    @property
    def permissions(self):
        try:
            return json.loads(self.permissions_json or '[]')
        except (TypeError, ValueError):
            return []

    def can_access(self, module):
        """Pode AGIR no módulo (criar, editar, excluir)."""
        r = self._effective_role()
        if r == 'master':
            return True
        return module in MODULOS_DO_PERFIL.get(r, ())

    def can_view(self, module):
        """Pode ABRIR a tela do módulo. A diretoria lê tudo."""
        return self.can_access(module) or self._effective_role() == 'visualizador'

    def pode(self, permissao):
        """Uma permissão FINA. O administrador passa sempre; o gestor
        configura a passagem dos contratos dele sem precisar de concessão."""
        r = self._effective_role()
        if r == 'master':
            return True
        if r == 'pleno' and permissao == 'diario_config':
            return True
        return permissao in self.permissions

    def sees_client_data(self):
        """Pode agir sobre os dados dos contratos (gestor e administrador)."""
        return self._effective_role() in ('master', 'pleno')

    def le_dados_do_cliente(self):
        """Pode LER os dados dos contratos (inclui a diretoria)."""
        return self._effective_role() in ('master', 'pleno', 'visualizador')

    def e_encarregado(self):
        return self._effective_role() == 'encarregado'

    def e_tecnico(self):
        return self._effective_role() == 'tecnico'

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'email': self.email,
                'role': self._effective_role(), 'perfil': self.perfil_rotulo,
                'is_active': self.is_active, 'client_ids': self.client_ids,
                'all_clients': bool(self.all_clients)}


class Notification(db.Model):
    """Aviso dentro do sistema (sino do topo)."""
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    notification_type = db.Column(db.String(40), nullable=False, default='geral')
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text)
    link = db.Column(db.String(255))
    status = db.Column(db.String(10), default='unread', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
