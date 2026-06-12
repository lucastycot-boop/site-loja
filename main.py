from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = "chave_secreta_super_segura_para_loja"

# CONFIGURAÇÃO DE UPLOAD DE IMAGENS
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# CONFIGURAÇÃO INTELIGENTE DO POSTGRESQL (LOCAL OU PRODUÇÃO)
# Se a Render fornecer a URL do banco (DATABASE_URL), ele usa. Se não, usa o seu localhost.
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'postgresql://postgres:0408@localhost:5432/loja_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Função para validar se o arquivo é realmente uma imagem permitida
def arquivo_permitido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==========================================
# MODELOS DO BANCO DE DADOS (TABELAS)
# ==========================================

class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    senha = db.Column(db.String(255), nullable=False)
    eh_admin = db.Column(db.Boolean, default=False)

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    preco = db.Column(db.Float, nullable=False)
    estoque = db.Column(db.Integer, default=0)
    categoria = db.Column(db.String(50), nullable=True)
    imagem_url = db.Column(db.String(200), nullable=True)
    tamanho = db.Column(db.String(10), nullable=True)

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
# ROTAS DO CARRINHO DE COMPRAS
# ==========================================

@app.route('/carrinho/adicionar/<int:id>', methods=['POST'])
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
    return redirect(url_for('exibir_carrinho'))

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

@app.route('/carrinho/remover/<int:id>', methods=['POST'])
def remover_carrinho(id):
    carrinho = session.get('carrinho', {})
    id_str = str(id)

    if id_str in carrinho:
        carrinho.pop(id_str)
        session['carrinho'] = carrinho
        flash('Item removido do carrinho.', 'info')

    return redirect(url_for('exibir_carrinho'))

# ==========================================
# ROTAS DE SISTEMA (CADASTRO E LOGIN)
# ==========================================

@app.route("/cadastro", methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')

        usuario_existe = Usuario.query.filter_by(email=email).first()
        if usuario_existe:
            flash('Este e-mail já está cadastrado.', 'warning')
            return redirect(url_for('cadastro'))

        senha_cripto = generate_password_hash(senha, method='scrypt')

        novo_usuario = Usuario(nome=nome, email=email, senha=senha_cripto, eh_admin=True)
        db.session.add(novo_usuario)
        db.session.commit()

        flash('Cadastro realizado com sucesso! Faça seu login.', 'success')
        return redirect(url_for('login'))

    return render_template("cadastro.html")

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')

        usuario = Usuario.query.filter_by(email=email).first()

        if usuario and check_password_hash(usuario.senha, senha):
            session['usuario_id'] = usuario.id
            session['usuario_nome'] = usuario.nome
            session['eh_admin'] = usuario.eh_admin

            flash(f'Bem-vindo de volta, {usuario.nome}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('E-mail ou senha incorretos.', 'danger')

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('index'))

# ==========================================
# PAINEL ADMINISTRATIVO (ADMIN)
# ==========================================

@app.route("/admin")
@admin_requerido
def painel_admin():
    produtos = Produto.query.all()
    usuarios = Usuario.query.all()
    return render_template("admin.html", produtos=produtos, usuarios=usuarios)

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

        nome_imagem = None

        if 'imagem_arquivo' in request.files:
            arquivo = request.files['imagem_arquivo']
            if arquivo and arquivo.filename != '' and arquivo_permitido(arquivo.filename):
                nome_imagem = secure_filename(arquivo.filename)
                arquivo.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_imagem))

        produto = Produto(
            nome=nome,
            descricao=descricao,
            preco=preco,
            estoque=estoque,
            imagem_url=nome_imagem,
            categoria=categoria,
            tamanho=tamanho
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

    if produto.imagem_url:
        caminho_foto = os.path.join(app.config['UPLOAD_FOLDER'], produto.imagem_url)
        if os.path.exists(caminho_foto):
            os.remove(caminho_foto)

    db.session.delete(produto)
    db.session.commit()
    flash(f'Produto "{produto.nome}" removido completamente!', 'success')
    return redirect(url_for('painel_admin'))

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    # Configuração de porta dinâmica para servidores de hospedagem
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
