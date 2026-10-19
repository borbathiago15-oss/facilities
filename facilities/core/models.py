"""O núcleo: quem entra (User), em que contrato (Client) e os avisos.

Os nomes internos são os mesmos do Trino Intelligence, de onde a Passagem de
Turno veio: ``User.name``, ``Client.cost_center``, ``client_id`` nas tabelas
do módulo, os perfis ``master``/``pleno``/``encarregado``. Não é preguiça de
traduzir — é o que permite trazer o módulo e os seus testes quase sem
alteração, e com eles as regras que custaram para acertar (contagem por área,
rascunho fora dos indicadores, tarefa sem resposta...). Na TELA tudo fala a
língua do Facilities: "contrato", "gestor", "técnico".

Perfis (``role``) e o que cada um faz — de cima para baixo na cadeia
(Fase 2: cada pessoa tem um superior direto, e quem está acima vê tudo o que
os de baixo veem):

* ``master``       — Administrador: tudo, todos os locais, cadastros. Fora da cadeia.
* ``visualizador`` — Diretoria: lê tudo, não altera nada. Fora da cadeia.
* ``gerente``      — Gerente: responsável por clientes; vê todos os locais dos
                     clientes dele e tudo da sua equipe; age como gestor.
* ``pleno``        — Coordenador (o antigo "gestor", nome interno herdado do
                     Trino): os locais dele e da equipe; configura a passagem,
                     pede tarefas, acompanha painel e chamados.
* ``supervisor``   — Supervisor: acompanha a equipe dos locais dele e também
                     faz a passagem/checklist.
* ``encarregado``  — Encarregado ou ASG: faz a passagem/checklist e abre chamados.
* ``tecnico``      — Técnico de manutenção (nível do encarregado): atende os
                     chamados e faz a passagem da equipe dele.
* ``cliente``      — Usuário do cliente: só entra no portal (``/cliente``),
                     com a segunda etapa, e só com ``CLIENTE_EXTERNO_LIBERADO``
                     ligado (Fase 9B; padrão desligado).
"""
import json
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from facilities.extensions import db

PERFIS = {
    'master': 'Administrador',
    'visualizador': 'Diretoria (só leitura)',
    'gerente': 'Gerente',
    'pleno': 'Coordenador',
    'supervisor': 'Supervisor',
    'encarregado': 'Encarregado / ASG',
    'tecnico': 'Técnico de manutenção',
    'cliente': 'Cliente (portal do cliente)',
}

# Quem age como gestor nos locais que vê (configura, atribui, cobra).
PERFIS_DE_GESTAO = ('master', 'gerente', 'pleno')

# A cadeia: o superior direto precisa estar num nível ACIMA (número menor).
# Pular nível vale (encarregado direto sob o coordenador, num local sem
# supervisor). Administrador, diretoria e cliente ficam fora da cadeia.
NIVEL_NA_CADEIA = {'gerente': 1, 'pleno': 2, 'supervisor': 3,
                   'encarregado': 4, 'tecnico': 4}

# Segunda etapa obrigatória (auditoria SEC-001, decisão do dono 19/10/2026):
# quem enxerga vários locais não entra só com a senha. O cliente já era
# obrigado (Fase 9B).
PERFIS_COM_SEGUNDA_ETAPA = PERFIS_DE_GESTAO + ('visualizador',)

# O perfil cliente existe desde a Fase 2; entra no portal só com
# CLIENTE_EXTERNO_LIBERADO ligado (Fase 9B).
PERFIS_SEM_LOGIN = ('cliente',)

# Os módulos com tela. O nome da passagem é o mesmo do Trino
# (``diario_operacional``) pelo motivo do topo deste arquivo.
MODULO_PASSAGEM = 'diario_operacional'
MODULO_CHAMADOS = 'chamados'
MODULES = [MODULO_PASSAGEM, MODULO_CHAMADOS]

# Quem AGE em cada módulo, por perfil. O perfil decide sozinho — não há
# caixinha de módulo no cadastro: um clique errado não abre nada a ninguém.
MODULOS_DO_PERFIL = {
    'gerente': (MODULO_PASSAGEM, MODULO_CHAMADOS),
    'pleno': (MODULO_PASSAGEM, MODULO_CHAMADOS),
    'supervisor': (MODULO_PASSAGEM, MODULO_CHAMADOS),
    'encarregado': (MODULO_PASSAGEM, MODULO_CHAMADOS),
    'tecnico': (MODULO_PASSAGEM, MODULO_CHAMADOS),
    'visualizador': (),
    'cliente': (),
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
    # Sobe a cada troca de senha/desativação/saída: derruba as sessões abertas.
    session_epoch = db.Column(db.Integer, default=0, nullable=False)
    # A cadeia (Fase 2): o superior direto. Ver ``core/hierarquia.py``.
    superior_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                            nullable=True, index=True)
    # Só para o perfil cliente: de qual cliente (contratante) ele é.
    cliente_id = db.Column(db.Integer, db.ForeignKey('contratantes.id', ondelete='RESTRICT'),
                           nullable=True, index=True)
    # Segunda etapa do login (TOTP, ``core/totp.py``). O segredo só vale com
    # ``totp_ativo``; o último passo aceito barra o mesmo código duas vezes.
    totp_segredo = db.Column(db.String(64), nullable=True)
    totp_ativo = db.Column(db.Boolean, default=False, nullable=False,
                           server_default=db.false())
    totp_ultimo_passo = db.Column(db.BigInteger, nullable=True)
    # Erros de código guardados NO SERVIDOR (auditoria SEC-003): antes a conta
    # ficava no cookie, e repetir o cookie antigo zerava as tentativas. O
    # login com a senha certa não zera; só o código certo.
    totp_falhas = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    totp_bloqueio_ate = db.Column(db.DateTime, nullable=True)

    clients = db.relationship('Client', secondary=user_clients, backref='linked_users')
    superior = db.relationship('User', remote_side=[id], foreign_keys=[superior_id],
                               backref='subordinados_diretos')

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
        if r in PERFIS_DE_GESTAO and permissao == 'diario_config':
            return True
        return permissao in self.permissions

    def sees_client_data(self):
        """Pode agir sobre os dados dos locais (gestão: gerente, coordenador,
        administrador)."""
        return self._effective_role() in PERFIS_DE_GESTAO

    def e_gestao(self):
        return self._effective_role() in PERFIS_DE_GESTAO

    def le_dados_do_cliente(self):
        """Pode LER os dados dos locais (inclui a diretoria)."""
        return self._effective_role() in PERFIS_DE_GESTAO + ('visualizador',)

    def e_encarregado(self):
        return self._effective_role() == 'encarregado'

    def e_tecnico(self):
        return self._effective_role() == 'tecnico'

    def e_supervisor(self):
        return self._effective_role() == 'supervisor'

    @property
    def nivel(self):
        return NIVEL_NA_CADEIA.get(self._effective_role())

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'email': self.email,
                'role': self._effective_role(), 'perfil': self.perfil_rotulo,
                'is_active': self.is_active, 'client_ids': self.client_ids,
                'all_clients': bool(self.all_clients), 'superior_id': self.superior_id}


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


class PushInscricao(db.Model):
    """Um celular (navegador) que aceitou receber avisos (Web Push, Fase 4B).

    O endereço é do serviço de push do navegador (Google, Mozilla, Apple,
    Microsoft) — ``core/push.py`` só aceita esses. Uma pessoa pode ter
    vários aparelhos; o serviço respondeu 404/410 → a inscrição sai.
    """
    __tablename__ = 'push_inscricoes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
                        nullable=False, index=True)
    endpoint = db.Column(db.String(600), nullable=False, unique=True)
    p256dh = db.Column(db.String(200), nullable=False)
    auth = db.Column(db.String(100), nullable=False)
    aparelho = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ultimo_envio_em = db.Column(db.DateTime)
    falhas = db.Column(db.Integer, default=0, nullable=False)
