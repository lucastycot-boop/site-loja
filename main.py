from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import os
import random
import string
from sqlalchemy import func

app = Flask(__name__)
app.secret_key = "chave_secreta_super_segura_para_loja"
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# CONFIGURAÇÃO DE UPLOAD DE IMAGENS
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# CONFIGURAÇÃO DO BANCO DE DADOS POSTGRESQL
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'postgresql://postgres:0408@localhost:5432/loja_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

def arquivo_permitido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==========================================
# MODELOS DO BANCO DE DADOS (TABELAS)
# ==========================================

class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=True)   # Opcional para novos, obrigatório para antigos
    whatsapp = db.Column(db.String(20), unique=True, nullable=True) # Opcional para antigos, obrigatório para novos
    senha = db.Column(db.String(255), nullable=False)
    eh_admin = db.Column(db.Boolean, default=False)

class Produto(db.Model):
    __tablename__ = 'produtos_v2'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    preco = db.Column(db.Float, nullable=False)
    estoque = db.Column(db.Integer, default=0)
    categoria = db.Column(db.String(50), nullable=True)
    tamanho = db.Column(db.String(10), nullable=True)
    imagem_url = db.Column(db.String(200), nullable=True)
    imagem_url2 = db.Column(db.String(200), nullable=True)
    imagem_url3 = db.Column(db.String(200), nullable=True)

class Pedido(db.Model):
    __tablename__ = 'pedidos'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    cliente_nome = db.Column(db.String(100), nullable=False)
    produtos_resumo = db.Column(db.Text, nullable=False)
    total = db.Column(db.Float, nullable=False)
    codigo_rastreio = db.Column(db.String(20), unique=True, nullable=False)
    status = db.Column(db.String(50), default="Pedido Recebido")
    forma_pagamento = db.Column(db.String(50), nullable=False)

    usuario = db.relationship('Usuario', backref=db.backref('pedidos', lazy=True))

# ==========================================
# DECORATORS PARA PROTEGER PÁGINAS
# ==========================================
def login_requerido(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Por favor, faça login para acessar esta página.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_requerido(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session or not session.get('eh_admin'):
            flash('Acesso negado. Apenas administradores podem entrar aqui.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# ROTAS PÚBLICAS (VITRINE E PRODUTOS)
# ==========================================

@app.route('/quem-somos')
def quem_somos():
    return render_template('quem_somos.html')

@app.route('/')
def index():
    busca = request.args.get('q', '').strip()
    categoria_filtrada = request.args.get('categoria', '').strip()
    ordenar_por = request.args.get('ordem', '').strip()

    query = Produto.query

    if categoria_filtrada:
        query = query.filter(Produto.categoria.ilike(categoria_filtrada))

    if busca:
        query = query.filter(
            (Produto.nome.ilike(f'%{busca}%')) |
            (Produto.descricao.ilike(f'%{busca}%')) |
            (Produto.categoria.ilike(f'%{busca}%'))
        )

    if ordenar_por == 'preco_min':
        query = query.order_by(Produto.preco.asc())
    elif ordenar_por == 'preco_max':
        query = query.order_by(Produto.preco.desc())
    elif ordenar_por == 'novidades':
        query = query.order_by(Produto.id.desc())

    produtos = query.all()

    categorias_no_banco = Produto.query.with_entities(Produto.categoria).distinct().all()
    categorias = [cat[0] for cat in categorias_no_banco if cat[0]]

    return render_template('index.html', produtos=produtos, categories=categorias, busca=busca, categoria_atual=categoria_filtrada, ordem_atual=ordenar_por)

@app.route("/produto/<int:id>")
def detalhe_produto(id):
    produto = Produto.query.get_or_404(id)
    return render_template("produto.html", produto=produto)

# ==========================================
# ROTAS DO CARRINHO E PEDIDOS
# ==========================================

@app.route('/carrinho/adicionar/<int:id>', methods=['GET', 'POST'])
def adicionar_carrinho(id):
    if 'carrinho' not in session:
        session['carrinho'] = {}

    carrinho = session['carrinho']
    id_str = str(id)

    if id_str in carrinho:
        carrinho[id_str] += 1
    else:
        carrinho[id_str] = 1

    session['carrinho'] = carrinho
    flash('Peça adicionada ao seu carrinho!', 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/carrinho')
def exibir_carrinho():
    carrinho = session.get('carrinho', {})
    produtos_carrinho = []
    total = 0.0

    for id_str, quantidade in carrinho.items():
        produto = Produto.query.get(int(id_str))
        if produto:
            subtotal = produto.preco * quantidade
            total += subtotal
            produtos_carrinho.append({
                'produto': produto,
                'quantidade': quantidade,
                'subtotal': subtotal
            })

    return render_template('carrinho.html', itens=produtos_carrinho, total=total)

@app.route('/carrinho/checkout')
def checkout_pagamento():
    carrinho = session.get('carrinho', {})
    produtos_carrinho = []
    total = 0.0

    for id_str, quantity in carrinho.items():
        produto = Produto.query.get(int(id_str))
        if produto:
            subtotal = produto.preco * quantity
            total += subtotal
            produtos_carrinho.append({
                'produto': produto,
                'quantidade': quantity,
                'subtotal': subtotal
            })

    if not produtos_carrinho:
        flash('Sua sacola está vazia!', 'warning')
        return redirect(url_for('index'))

    return render_template('checkout.html', itens=produtos_carrinho, total=total)

@app.route('/carrinho/simular-pedido', methods=['POST'])
def simular_pedido():
    carrinho = session.get('carrinho', {})
    if not carrinho:
        return redirect(url_for('index'))

    resumo_pecas = []
    total = 0.0
    for id_str, qte in carrinho.items():
        p = Produto.query.get(int(id_str))
        if p:
            total += (p.preco * qte)
            resumo_pecas.append(f"{p.nome} (x{qte})")

    numeros = ''.join(random.choices(string.digits, k=6))
    codigo = f"VC{numeros}BR"

    nome_cliente = session.get('usuario_nome', request.form.get('cardholderName', 'Cliente Espaço VC'))
    user_id = session.get('usuario_id', None)

    forma_pag = "Cartão de Crédito" if request.form.get('cardholderName') else "PIX"

    novo_pedido = Pedido(
        usuario_id=user_id,
        cliente_nome=nome_cliente,
        produtos_resumo=", ".join(resumo_pecas),
        total=total,
        codigo_rastreio=codigo,
        status="Pedido Recebido",
        forma_pagamento=forma_pag
    )
    db.session.add(novo_pedido)
    db.session.commit()

    session.pop('carrinho', None)
    return redirect(url_for('rastrear_pedido_codigo', codigo=codigo))

@app.route('/rastreio/<codigo>')
def rastrear_pedido_codigo(codigo):
    pedido = Pedido.query.filter_by(codigo_rastreio=codigo).first_or_404()
    return render_template('rastreio.html', pedido=pedido)

@app.route('/minhas-compras')
@login_requerido
def minhas_compras():
    user_id = session.get('usuario_id')
    pedidos_cliente = Pedido.query.filter_by(usuario_id=user_id).order_by(Pedido.id.desc()).all()
    return render_template('minhas_compras.html', pedidos=pedidos_cliente)

@app.route('/carrinho/remover/<int:id>', methods=['POST'])
def remover_carrinho(id):
    carrinho = session.get('carrinho', {})
    id_str = str(id)

    if id_str in carrinho:
        if carrinho[id_str] > 1:
            carrinho[id_str] -= 1
            flash('Uma unidade foi removida da sacola.', 'info')
        else:
            carrinho.pop(id_str)
            flash('Item removido da sacola.', 'info')
        session['carrinho'] = carrinho

    return redirect(url_for('exibir_carrinho'))

# ==========================================
# ROTAS DE SISTEMA (LOGIN E CADASTRO INTELIGENTES)
# ==========================================

@app.route("/cadastro", methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email', '').strip().lower()
        whatsapp = request.form.get('whatsapp', '').strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        senha = request.form.get('senha')

        if not whatsapp:
            flash('O número de WhatsApp é obrigatório para o cadastro.', 'warning')
            return redirect(url_for('cadastro'))

        # Validações de duplicidade amigáveis
        if email:
            email_existe = Usuario.query.filter_by(email=email).first()
            if email_existe:
                flash('Este e-mail já está sendo utilizado.', 'warning')
                return redirect(url_for('cadastro'))

        whatsapp_existe = Usuario.query.filter_by(whatsapp=whatsapp).first()
        if whatsapp_existe:
            flash('Este número de WhatsApp já está cadastrado.', 'warning')
            return redirect(url_for('cadastro'))

        senha_cripto = generate_password_hash(senha, method='scrypt')

        # Cria a conta salvando e-mail (se digitado) e o WhatsApp obrigatoriamente
        novo_usuario = Usuario(nome=nome, email=email if email else None, whatsapp=whatsapp, senha=senha_cripto, eh_admin=False)
        db.session.add(novo_usuario)
        db.session.commit()

        flash('Cadastro realizado com sucesso! Use seu WhatsApp ou E-mail para entrar.', 'success')
        return redirect(url_for('login'))

    return render_template("cadastro.html")

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_input = request.form.get('login_input', '').strip()
        senha = request.form.get('senha')

        # Trata o campo de texto caso seja um número com traços/parênteses
        login_limpo = login_input.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')

        # Busca Híbrida: Compara com a coluna whatsapp ou com a coluna email
        usuario = Usuario.query.filter((Usuario.whatsapp == login_limpo) | (Usuario.email == login_input.lower())).first()

        if usuario and check_password_hash(usuario.senha, senha):
            session['usuario_id'] = usuario.id
            session['usuario_name'] = usuario.nome
            session['usuario_nome'] = usuario.nome
            session['eh_admin'] = usuario.eh_admin

            flash(f'Bem-vindo de volta, {usuario.nome}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Dados de acesso incorretos. Verifique as suas credenciais.', 'danger')

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('index'))

# ==========================================
# PAINEL ADMINISTRATIVO (ADM)
# ==========================================

@app.route("/admin")
@admin_requerido
def painel_admin():
    produtos = Produto.query.all()
    pedidos = Pedido.query.order_by(Pedido.id.desc()).all()

    usuarios_lista = Usuario.query.all()
    for u in usuarios_lista:
        total_gasto = db.session.query(func.sum(Pedido.total)).filter(
            Pedido.usuario_id == u.id,
            ~Pedido.status.like('%Cancelado%')
        ).scalar()

        u.total_gasto = total_gasto if total_gasto else 0.0

    ranking_clientes = sorted(usuarios_lista, key=lambda x: x.total_gasto, reverse=True)

    return render_template("admin.html", produtos=produtos, usuarios=ranking_clientes, pedidos=pedidos)

@app.route("/admin/pedido/status/<int:id>", methods=['POST'])
@admin_requerido
def atualizar_status_pedido(id):
    pedido = Pedido.query.get_or_404(id)
    novo_status = request.form.get('status')

    if novo_status:
        pedido.status = novo_status
        db.session.commit()
        flash(f'Status do pedido {pedido.codigo_rastreio} atualizado para "{novo_status}"!', 'success')

    return redirect(url_for('painel_admin'))

@app.route('/pedido/cancelar/<int:id>', methods=['POST'])
@login_requerido
def cancelar_pedido_cliente(id):
    pedido = Pedido.query.get_or_404(id)

    if pedido.usuario_id != session.get('usuario_id'):
        flash('Acesso negado.', 'danger')
        return redirect(url_for('minhas_compras'))

    if pedido.status in ['Pedido Recebido', 'Pagamento Confirmado']:
        pedido.status = "Cancelado pelo Cliente"
        db.session.commit()
        flash('Seu pedido foi cancelado com sucesso.', 'info')
    else:
        flash('Este pedido já está em processo de envio e não pode ser cancelado pelo site.', 'warning')

    return redirect(url_for('minhas_compras'))

@app.route('/admin/pedido/deletar/<int:id>', methods=['POST'])
@admin_requerido
def deletar_pedido_admin(id):
    pedido = Pedido.query.get_or_404(id)
    db.session.delete(pedido)
    db.session.commit()
    flash(f'Pedido {pedido.codigo_rastreio} removido permanentemente!', 'success')
    return redirect(url_for('painel_admin'))

@app.route("/admin/usuario/alternar-admin/<int:id>", methods=['POST'])
@admin_requerido
def alternar_admin(id):
    usuario = Usuario.query.get_or_404(id)

    if usuario.id == session.get('usuario_id'):
        flash('Você não pode alterar suas próprias permissões!', 'danger')
        return redirect(url_for('painel_admin'))

    usuario.eh_admin = not usuario.eh_admin
    db.session.commit()

    status = "promovido a Administrador" if usuario.eh_admin else "rebaixado para Usuário Comum"
    flash(f'Usuário {usuario.nome} foi {status}!', 'success')
    return redirect(url_for('painel_admin'))

@app.route("/admin/produto/novo", methods=['GET', 'POST'])
@admin_requerido
def novo_produto():
    if request.method == 'POST':
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        preco = float(request.form.get('preco'))
        estoque = int(request.form.get('estoque'))
        categoria = request.form.get('categoria')
        tamanho = request.form.get('tamanho')

        nomes_imagens = [None, None, None]

        for i in range(1, 4):
            campo_nome = f'imagem_arquivo{i}' if i > 1 else 'imagem_arquivo'
            if campo_nome in request.files:
                arquivo = request.files[campo_nome]
                if arquivo and arquivo.filename != '' and arquivo_permitido(arquivo.filename):
                    nome_seguro = secure_filename(arquivo.filename)
                    nome_final = f"foto{i}_{nome_seguro}"
                    arquivo.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_final))
                    nomes_imagens[i-1] = nome_final

        produto = Produto(
            nome=nome,
            descricao=descricao,
            preco=preco,
            estoque=estoque,
            categoria=categoria,
            tamanho=tamanho,
            imagem_url=nomes_imagens[0],
            imagem_url2=nomes_imagens[1],
            imagem_url3=nomes_imagens[2]
        )
        db.session.add(produto)
        db.session.commit()

        flash('Produto cadastrado com sucesso!', 'success')
        return redirect(url_for('painel_admin'))

    return render_template("novo_produto.html")

@app.route("/admin/produto/deletar/<int:id>", methods=['POST'])
@admin_requerido
def deletar_produto(id):
    produto = Produto.query.get_or_404(id)

    for campo_foto in [produto.imagem_url, produto.imagem_url2, produto.imagem_url3]:
        if campo_foto:
            caminho_foto = os.path.join(app.config['UPLOAD_FOLDER'], campo_foto)
            if os.path.exists(caminho_foto):
                os.remove(caminho_foto)

    db.session.delete(produto)
    db.session.commit()
    flash(f'Produto "{produto.nome}" removido completamente!', 'success')
    return redirect(url_for('painel_admin'))


# ==========================================
# SISTEMA DE ATUALIZAÇÃO AUTOMÁTICA DO BANCO
# ==========================================
with app.app_context():
    db.create_all() # Cria novas tabelas se não existirem

    # Adiciona a coluna sem apagar seus clientes e e-mails antigos
    try:
        db.session.execute(db.text("ALTER TABLE usuarios ADD COLUMN whatsapp VARCHAR(20) UNIQUE;"))
        db.session.execute(db.text("ALTER TABLE usuarios ALTER COLUMN email DROP NOT NULL;"))
        db.session.commit()
        print(">> Coluna WhatsApp criada com sucesso e e-mail flexibilizado!")
    except Exception as e:
        db.session.rollback() # Ignora o erro se a coluna já existia


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
