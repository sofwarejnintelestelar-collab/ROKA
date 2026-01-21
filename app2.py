# ==============================
# IMPORTS CORRECTOS
# ==============================
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
import psycopg2
from datetime import datetime, date, timedelta
import json
import hashlib
from functools import wraps
from flask_socketio import SocketIO, emit, join_room, leave_room
import socket
import os
import locale
from urllib.parse import urlparse

# Configurar locale para español
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'es_ES')
    except:
        pass

app = Flask(__name__)
app.secret_key = 'clave_secreta_pos_2024_sistema_login'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ==============================
# FILTROS PERSONALIZADOS
# ==============================
def format_datetime(value, format='medium'):
    if value is None: return ""
    if isinstance(value, str):
        try:
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
                try:
                    value = datetime.strptime(value, fmt)
                    break
                except: continue
        except: return value
    
    if format == 'full': format_str = "%A, %d de %B de %Y, %H:%M:%S"
    elif format == 'medium': format_str = "%d/%m/%Y %H:%M:%S"
    elif format == 'short': format_str = "%d/%m/%Y"
    elif format == 'time': format_str = "%H:%M:%S"
    elif format == 'date': format_str = "%d/%m/%Y"
    elif format == 'hora_corta': format_str = "%H:%M"
    else: format_str = str(format)
    
    try: return value.strftime(format_str)
    except: return str(value)

def format_currency(value):
    if value is None: return "$0.00"
    try:
        value = float(value)
        return f"${value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except: return f"${value}"

def format_number(value):
    if value is None: return "0"
    try:
        value = float(value)
        if value.is_integer(): return f"{int(value):,}".replace(',', '.')
        else: return f"{value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except: return str(value)

app.jinja_env.filters['format_datetime'] = format_datetime
app.jinja_env.filters['format_currency'] = format_currency
app.jinja_env.filters['format_number'] = format_number

# ==============================
# CONEXIÓN A BASE DE DATOS - SOLUCIÓN DEFINITIVA
# ==============================
def get_db_connection():
    database_url = os.environ.get("DATABASE_URL")

    if database_url:
        # Render / Producción
        print("🌐 Conectando a base de datos de Render...")
        result = urlparse(database_url)
        return psycopg2.connect(
            host=result.hostname,
            database=result.path[1:],  # Elimina el '/' inicial
            user=result.username,
            password=result.password,
            port=result.port,
            sslmode="require"
        )
    else:
        # Local (tu PC) - SOLO PARA DESARROLLO
        print("💻 Conectando a base de datos local...")
        return psycopg2.connect(
            host="localhost",
            database="roka",
            user="postgres",
            password="pm",
            port=5432
        )

# ==============================
# CREACIÓN DE TABLAS (SI NO EXISTEN)
# ==============================
def create_tables():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        print("📝 Creando tablas si no existen...")
        
        # Tablas existentes (solo si no existen)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                nombre VARCHAR(100) NOT NULL,
                email VARCHAR(100),
                rol VARCHAR(20) DEFAULT 'cajero',
                activo BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS caja_turnos (
                id SERIAL PRIMARY KEY,
                fecha_apertura TIMESTAMP NOT NULL,
                fecha_cierre TIMESTAMP,
                monto_inicial DECIMAL(10,2) NOT NULL DEFAULT 0,
                monto_final_real DECIMAL(10,2),
                total_ventas DECIMAL(10,2) DEFAULT 0,
                monto_esperado DECIMAL(10,2),
                diferencia DECIMAL(10,2),
                observaciones TEXT,
                estado VARCHAR(20) DEFAULT 'abierta',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS categorias (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS proveedores (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(200) NOT NULL,
                contacto VARCHAR(100),
                telefono VARCHAR(20),
                email VARCHAR(100),
                direccion TEXT,
                activo BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS mesas (
                id SERIAL PRIMARY KEY,
                numero INTEGER UNIQUE NOT NULL,
                capacidad INTEGER DEFAULT 4,
                estado VARCHAR(20) DEFAULT 'disponible',
                ubicacion VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS productos (
                id SERIAL PRIMARY KEY,
                codigo_barra VARCHAR(50) UNIQUE,
                nombre VARCHAR(200) NOT NULL,
                precio DECIMAL(10,2) NOT NULL,
                stock INTEGER DEFAULT 0,
                categoria_id INTEGER,
                proveedor_id INTEGER,
                tipo VARCHAR(20) DEFAULT 'producto',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (categoria_id) REFERENCES categorias(id) ON DELETE SET NULL,
                FOREIGN KEY (proveedor_id) REFERENCES proveedores(id) ON DELETE SET NULL
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ordenes (
                id SERIAL PRIMARY KEY,
                mesa_id INTEGER NOT NULL,
                mozo_nombre VARCHAR(100) NOT NULL,
                estado VARCHAR(20) DEFAULT 'abierta',
                observaciones TEXT,
                total DECIMAL(10,2) DEFAULT 0,
                fecha_apertura TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_cierre TIMESTAMP,
                dispositivo_origen VARCHAR(100),
                FOREIGN KEY (mesa_id) REFERENCES mesas(id) ON DELETE CASCADE
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS orden_items (
                id SERIAL PRIMARY KEY,
                orden_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                producto_nombre VARCHAR(200) NOT NULL,
                cantidad INTEGER NOT NULL,
                precio_unitario DECIMAL(10,2) NOT NULL,
                observaciones TEXT,
                estado_item VARCHAR(20) DEFAULT 'pendiente',
                tiempo_inicio TIMESTAMP,
                tiempo_fin TIMESTAMP,
                tiempo_estimado INTEGER DEFAULT 15,
                FOREIGN KEY (orden_id) REFERENCES ordenes(id) ON DELETE CASCADE,
                FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE SET NULL
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS cierres_caja (
                id SERIAL PRIMARY KEY,
                turno_id INTEGER,
                fecha_cierre TIMESTAMP NOT NULL,
                monto_total DECIMAL(10,2) NOT NULL,
                monto_efectivo DECIMAL(10,2),
                monto_tarjeta DECIMAL(10,2),
                monto_transferencia DECIMAL(10,2),
                observaciones TEXT,
                usuario_cierre VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (turno_id) REFERENCES caja_turnos(id) ON DELETE SET NULL
            )
        ''')
        
        # Insertar usuarios por defecto si no existen
        cur.execute("SELECT COUNT(*) FROM usuarios WHERE username = 'admin'")
        if cur.fetchone()[0] == 0:
            print("👤 Creando usuarios por defecto...")
            password_hash = hashlib.sha256('admin123'.encode()).hexdigest()
            cur.execute('INSERT INTO usuarios (username, password_hash, nombre, email, rol) VALUES (%s, %s, %s, %s, %s)', 
                       ('admin', password_hash, 'Administrador', 'admin@sistema.com', 'admin'))
            cur.execute('INSERT INTO usuarios (username, password_hash, nombre, email, rol) VALUES (%s, %s, %s, %s, %s)', 
                       ('mozo', hashlib.sha256('mozo123'.encode()).hexdigest(), 'Mozo Principal', 'mozo@sistema.com', 'mozo'))
            cur.execute('INSERT INTO usuarios (username, password_hash, nombre, email, rol) VALUES (%s, %s, %s, %s, %s)', 
                       ('chef', hashlib.sha256('chef123'.encode()).hexdigest(), 'Chef Principal', 'chef@sistema.com', 'chef'))
            cur.execute('INSERT INTO usuarios (username, password_hash, nombre, email, rol) VALUES (%s, %s, %s, %s, %s)', 
                       ('cajero', hashlib.sha256('cajero123'.encode()).hexdigest(), 'Cajero Principal', 'cajero@sistema.com', 'cajero'))
            
            # Insertar algunas mesas por defecto
            for i in range(1, 11):
                cur.execute('INSERT INTO mesas (numero, capacidad) VALUES (%s, %s) ON CONFLICT (numero) DO NOTHING', (i, 4))
            
            # Insertar algunas categorías
            categorias = ['ENTRADAS', 'PICADAS', 'EMPANADAS', 'PIZZAS', 'PLATOS ESPECIALES', 'POSTRES', 'BEBIDAS']
            for categoria in categorias:
                cur.execute('INSERT INTO categorias (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING', (categoria,))
        
        conn.commit()
        print("✅ Tablas creadas/verificadas exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error al crear tablas: {e}")
        return False
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

# ==============================
# CREAR TABLAS AL INICIAR (PARA RENDER/GUNICORN)
# ==============================
print("🚀 Inicializando aplicación ROKA...")
try:
    success = create_tables()
    if success:
        print("✅ Sistema listo para usar")
    else:
        print("⚠️  Las tablas pueden necesitar ser creadas manualmente")
        print("ℹ️  Visita /crear-tablas para crear las tablas")
except Exception as e:
    print(f"⚠️  Error durante inicialización: {e}")

# ==============================
# WEBSOCKETS GENERALES
# ==============================
@socketio.on('connect')
def handle_connect():
    print(f'✅ Cliente conectado: {request.sid}')
    emit('connection_response', {'status': 'connected', 'sid': request.sid})

@socketio.on('disconnect')
def handle_disconnect():
    print(f'❌ Cliente desconectado: {request.sid}')

# ==============================
# WEBSOCKETS ESPECÍFICOS PARA CHEF
# ==============================
@socketio.on('connect', namespace='/chef')
def handle_connect_chef():
    print(f'👨‍🍳 Chef conectado: {request.sid}')
    emit('connection_response', {'status': 'connected', 'rol': 'chef', 'message': 'Conexión establecida con cocina'}, namespace='/chef')

@socketio.on('disconnect', namespace='/chef')
def handle_disconnect_chef():
    print(f'👨‍🍳 Chef desconectado: {request.sid}')

@socketio.on('join_chef', namespace='/chef')
def handle_join_chef(data):
    usuario_id = data.get('usuario_id', 'invitado')
    print(f'👨‍🍳 Chef se unió al namespace cocina (Usuario: {usuario_id})')
    emit('join_response', {'status': 'joined', 'rol': 'chef', 'message': 'Bienvenido a la cocina'}, namespace='/chef')

# ==============================
# FUNCIONES DE AUTENTICACIÓN
# ==============================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, password_hash):
    return hash_password(password) == password_hash

def login_user(username, password):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, username, password_hash, nombre, rol FROM usuarios WHERE username = %s AND activo = true', (username,))
        usuario = cur.fetchone()
        if usuario and verify_password(password, usuario[2]):
            return {'id': usuario[0], 'username': usuario[1], 'nombre': usuario[3], 'rol': usuario[4]}
        return None
    except Exception as e:
        print(f"❌ Error específico en login: {e}")
        if "relation" in str(e) and "usuarios" in str(e):
            print("ℹ️  La tabla 'usuarios' no existe. Necesitas crear las tablas primero.")
        return None
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

def get_usuario_actual():
    if 'user_id' in session:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('SELECT id, username, nombre, rol FROM usuarios WHERE id = %s', (session['user_id'],))
            usuario = cur.fetchone()
            if usuario:
                return {'id': usuario[0], 'username': usuario[1], 'nombre': usuario[2], 'rol': usuario[3]}
        except Exception as e:
            print(f"❌ Error obteniendo usuario: {e}")
        finally:
            try:
                cur.close()
                conn.close()
            except:
                pass
    return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        usuario_actual = get_usuario_actual()
        if usuario_actual and usuario_actual['rol'] != 'admin':
            flash('Acceso restringido. Se requiere rol de administrador.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ==============================
# RUTAS PRINCIPALES
# ==============================
@app.route("/")
def index():
    """Página principal - Redirige a login"""
    return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    """Página de login"""
    if 'user_id' in session:
        usuario_actual = get_usuario_actual()
        if usuario_actual:
            if usuario_actual['rol'] == 'chef':
                return redirect(url_for('chef'))
            elif usuario_actual['rol'] == 'mozo':
                return redirect(url_for('ordenes'))
            elif usuario_actual['rol'] == 'admin':
                return redirect(url_for('productos'))
            else:
                return redirect(url_for('caja'))
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        usuario = login_user(username, password)
        
        if usuario:
            session['user_id'] = usuario['id']
            session['username'] = usuario['username']
            session['nombre'] = usuario['nombre']
            session['rol'] = usuario['rol']
            flash(f'Bienvenido {usuario["nombre"]}!', 'success')
            
            if usuario['rol'] == 'chef':
                return redirect(url_for('chef'))
            elif usuario['rol'] == 'mozo':
                return redirect(url_for('ordenes'))
            elif usuario['rol'] == 'admin':
                return redirect(url_for('productos'))
            else:
                return redirect(url_for('caja'))
        else:
            flash('Usuario o contraseña incorrectos. Si es la primera vez, primero crea las tablas.', 'danger')
    
    return render_template("login.html", 
                         ahora=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                         usuarios_default=[
                             {'username': 'admin', 'password': 'admin123', 'rol': 'Admin'},
                             {'username': 'chef', 'password': 'chef123', 'rol': 'Chef'},
                             {'username': 'mozo', 'password': 'mozo123', 'rol': 'Mozo'},
                             {'username': 'cajero', 'password': 'cajero123', 'rol': 'Cajero'}
                         ])

# ==============================
# RUTA PARA CREAR TABLAS MANUALMENTE
# ==============================
@app.route("/crear-tablas")
def crear_tablas_manual():
    """Ruta para crear tablas manualmente"""
    try:
        success = create_tables()
        if success:
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Tablas creadas</title>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                    .success { color: green; font-size: 24px; }
                    .info { color: blue; margin-top: 20px; }
                    a { color: #3498db; text-decoration: none; }
                </style>
            </head>
            <body>
                <div class="success">✅ Tablas creadas exitosamente!</div>
                <div class="info">Ahora puedes <a href="/login">iniciar sesión</a></div>
                <div class="info">
                    Usuarios creados:<br>
                    • admin / admin123<br>
                    • chef / chef123<br>
                    • mozo / mozo123<br>
                    • cajero / cajero123
                </div>
            </body>
            </html>
            '''
        else:
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Error</title>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                    .error { color: red; font-size: 18px; }
                </style>
            </head>
            <body>
                <div class="error">❌ Error al crear tablas. Revisa los logs.</div>
            </body>
            </html>
            '''
    except Exception as e:
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Error</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                .error {{ color: red; font-size: 18px; }}
            </style>
        </head>
        <body>
            <div class="error">❌ Error al crear tablas: {str(e)}</div>
        </body>
        </html>
        '''

# ==============================
# PANELES PRINCIPALES
# ==============================
@app.route("/caja")
@login_required
def caja():
    usuario_actual = get_usuario_actual()
    return render_template("caja.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/chef")
@login_required
def chef():
    usuario_actual = get_usuario_actual()
    return render_template("chef.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/ordenes")
@login_required
def ordenes():
    usuario_actual = get_usuario_actual()
    return render_template("ordenes.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/productos")
@login_required
def productos():
    usuario_actual = get_usuario_actual()
    search = request.args.get('search', '')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if search:
        cur.execute('''
            SELECT p.id, p.nombre, p.precio, p.stock, p.tipo, 
                   c.nombre as categoria_nombre
            FROM productos p 
            LEFT JOIN categorias c ON p.categoria_id = c.id
            WHERE p.nombre ILIKE %s
            ORDER BY p.nombre
        ''', (f'%{search}%',))
    else:
        cur.execute('''
            SELECT p.id, p.nombre, p.precio, p.stock, p.tipo, 
                   c.nombre as categoria_nombre
            FROM productos p 
            LEFT JOIN categorias c ON p.categoria_id = c.id
            ORDER BY p.nombre
        ''')
    
    productos_db = cur.fetchall()
    
    cur.execute('SELECT id, nombre FROM categorias ORDER BY nombre')
    categorias_db = cur.fetchall()
    
    productos_list = []
    for p in productos_db:
        productos_list.append({
            'id': p[0],
            'nombre': p[1],
            'precio': float(p[2]) if p[2] else 0.0,
            'stock': p[3] if p[3] is not None else 0,
            'tipo': p[4] if p[4] else 'producto',
            'categoria_nombre': p[5] if p[5] else 'Sin categoría'
        })
    
    cur.close()
    conn.close()
    
    return render_template("productos.html", 
                         usuario=usuario_actual,
                         productos=productos_list,
                         categorias=[{'id': c[0], 'nombre': c[1]} for c in categorias_db],
                         search=search,
                         ahora=datetime.now())

@app.route("/mesas")
@login_required
def mesas():
    usuario_actual = get_usuario_actual()
    search = request.args.get('search', '')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if search:
        cur.execute('SELECT * FROM mesas WHERE CAST(numero AS TEXT) ILIKE %s OR ubicacion ILIKE %s ORDER BY numero', 
                   (f'%{search}%', f'%{search}%'))
    else:
        cur.execute('SELECT * FROM mesas ORDER BY numero')
    
    mesas_db = cur.fetchall()
    mesas_list = []
    for mesa in mesas_db:
        mesas_list.append({
            'id': mesa[0],
            'numero': mesa[1],
            'capacidad': mesa[2],
            'estado': mesa[3],
            'ubicacion': mesa[4]
        })
    
    cur.close()
    conn.close()
    
    return render_template("mesas.html",
                         usuario=usuario_actual,
                         mesas=mesas_list,
                         search=search,
                         ahora=datetime.now())

@app.route("/categorias")
@login_required
def categorias():
    usuario_actual = get_usuario_actual()
    search = request.args.get('search', '')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if search:
        cur.execute('SELECT * FROM categorias WHERE nombre ILIKE %s ORDER BY nombre', (f'%{search}%',))
    else:
        cur.execute('SELECT * FROM categorias ORDER BY nombre')
    
    categorias_db = cur.fetchall()
    categorias_list = []
    for cat in categorias_db:
        categorias_list.append({
            'id': cat[0],
            'nombre': cat[1],
            'created_at': cat[2]
        })
    
    cur.close()
    conn.close()
    
    return render_template("categorias.html",
                         usuario=usuario_actual,
                         categorias=categorias_list,
                         search=search,
                         ahora=datetime.now())

@app.route("/proveedores")
@login_required
def proveedores():
    usuario_actual = get_usuario_actual()
    search = request.args.get('search', '')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if search:
        cur.execute('SELECT * FROM proveedores WHERE nombre ILIKE %s OR contacto ILIKE %s ORDER BY nombre', 
                   (f'%{search}%', f'%{search}%'))
    else:
        cur.execute('SELECT * FROM proveedores ORDER BY nombre')
    
    proveedores_db = cur.fetchall()
    proveedores_list = []
    for prov in proveedores_db:
        proveedores_list.append({
            'id': prov[0],
            'nombre': prov[1],
            'contacto': prov[2],
            'telefono': prov[3],
            'email': prov[4],
            'direccion': prov[5],
            'activo': prov[6]
        })
    
    cur.close()
    conn.close()
    
    return render_template("proveedores.html",
                         usuario=usuario_actual,
                         proveedores=proveedores_list,
                         search=search,
                         ahora=datetime.now())

@app.route("/ventas")
@login_required
def ventas():
    usuario_actual = get_usuario_actual()
    return render_template("ventas.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/historial_caja")
@login_required
def historial_caja():
    usuario_actual = get_usuario_actual()
    return render_template("historial_caja.html", usuario=usuario_actual, ahora=datetime.now())

# ==============================
# RUTAS DE CREACIÓN/EDICIÓN
# ==============================
@app.route("/crear_producto", methods=["GET", "POST"])
@login_required
def crear_producto():
    usuario_actual = get_usuario_actual()
    
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        precio = request.form.get("precio", "0")
        stock = request.form.get("stock", "0")
        categoria_id = request.form.get("categoria_id")
        tipo = request.form.get("tipo", "producto")
        
        if not nombre or not precio:
            flash('Nombre y precio son requeridos', 'danger')
            return redirect(url_for('crear_producto'))
        
        try:
            precio_float = float(precio)
            stock_int = int(stock) if stock else 0
            
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO productos (nombre, precio, stock, categoria_id, tipo) 
                VALUES (%s, %s, %s, %s, %s)
            ''', (nombre, precio_float, stock_int, categoria_id, tipo))
            
            conn.commit()
            flash(f'Producto "{nombre}" creado exitosamente', 'success')
            return redirect(url_for('productos'))
            
        except Exception as e:
            flash(f'Error al crear producto: {str(e)}', 'danger')
            return redirect(url_for('crear_producto'))
    
    # GET - mostrar formulario
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, nombre FROM categorias ORDER BY nombre')
    categorias = [{'id': c[0], 'nombre': c[1]} for c in cur.fetchall()]
    cur.close()
    conn.close()
    
    return render_template("crear_producto.html",
                         usuario=usuario_actual,
                         categorias=categorias,
                         ahora=datetime.now())

@app.route("/crear_mesa", methods=["GET", "POST"])
@login_required
def crear_mesa():
    usuario_actual = get_usuario_actual()
    
    if request.method == "POST":
        numero = request.form.get("numero")
        capacidad = request.form.get("capacidad", 4)
        ubicacion = request.form.get("ubicacion", "")
        
        if not numero:
            flash('Número de mesa requerido', 'danger')
            return redirect(url_for('crear_mesa'))
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('INSERT INTO mesas (numero, capacidad, ubicacion) VALUES (%s, %s, %s)', 
                       (numero, capacidad, ubicacion))
            conn.commit()
            flash(f'Mesa #{numero} creada exitosamente', 'success')
            return redirect(url_for('mesas'))
        except Exception as e:
            flash(f'Error al crear mesa: {str(e)}', 'danger')
            return redirect(url_for('crear_mesa'))
    
    return render_template("crear_mesa.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/crear_categoria", methods=["GET", "POST"])
@login_required
def crear_categoria():
    usuario_actual = get_usuario_actual()
    
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        
        if not nombre:
            flash('Nombre de categoría requerido', 'danger')
            return redirect(url_for('crear_categoria'))
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('INSERT INTO categorias (nombre) VALUES (%s)', (nombre,))
            conn.commit()
            flash(f'Categoría "{nombre}" creada exitosamente', 'success')
            return redirect(url_for('categorias'))
        except Exception as e:
            flash(f'Error al crear categoría: {str(e)}', 'danger')
            return redirect(url_for('crear_categoria'))
    
    return render_template("crear_categoria.html", usuario=usuario_actual, ahora=datetime.now())

# ==============================
# APIS PÚBLICAS
# ==============================
@app.route("/api/mesas")
def api_mesas():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, numero, capacidad, estado, ubicacion FROM mesas ORDER BY numero')
        mesas_db = cur.fetchall()
        mesas_list = []
        for m in mesas_db:
            mesas_list.append({
                'id': m[0], 
                'numero': m[1], 
                'capacidad': m[2], 
                'estado': m[3],
                'ubicacion': m[4]
            })
        return jsonify(mesas_list)
    except Exception as e:
        print(f"Error obteniendo mesas: {e}")
        return jsonify([])
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

@app.route("/api/productos")
def api_productos():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, nombre, precio, stock, tipo FROM productos ORDER BY nombre')
        productos_db = cur.fetchall()
        productos_list = []
        for p in productos_db:
            productos_list.append({
                'id': p[0], 
                'nombre': p[1],
                'precio': float(p[2]) if p[2] else 0.0,
                'stock': p[3] if p[3] is not None else 0,
                'tipo': p[4] if p[4] else 'producto'
            })
        return jsonify(productos_list)
    except Exception as e:
        print(f"Error obteniendo productos: {e}")
        return jsonify([])
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

@app.route("/api/categorias")
def api_categorias():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, nombre FROM categorias ORDER BY nombre')
        categorias_db = cur.fetchall()
        categorias_list = []
        for c in categorias_db:
            categorias_list.append({'id': c[0], 'nombre': c[1]})
        return jsonify(categorias_list)
    except Exception as e:
        print(f"Error obteniendo categorías: {e}")
        return jsonify([])
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

@app.route("/api/pedidos_cocina_comidas")
def api_pedidos_cocina_comidas():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT o.id as orden_id, m.numero as mesa_numero, o.mozo_nombre, 
                   json_agg(json_build_object(
                       'id', oi.id, 
                       'producto_nombre', oi.producto_nombre, 
                       'cantidad', oi.cantidad, 
                       'estado_item', COALESCE(oi.estado_item, 'pendiente')
                   )) as items
            FROM ordenes o 
            JOIN mesas m ON o.mesa_id = m.id 
            JOIN orden_items oi ON o.id = oi.orden_id
            WHERE o.estado IN ('abierta', 'proceso') 
            GROUP BY o.id, m.numero, o.mozo_nombre
            ORDER BY o.fecha_apertura ASC
        ''')
        pedidos_db = cur.fetchall()
        pedidos_list = []
        for pedido in pedidos_db:
            items = pedido[3] if pedido[3] else []
            pedidos_list.append({
                'id': pedido[0], 
                'mesa_numero': pedido[1], 
                'mozo_nombre': pedido[2],
                'items': items
            })
        return jsonify(pedidos_list)
    except Exception as e:
        print(f"Error obteniendo pedidos: {e}")
        return jsonify([])
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

@app.route("/api/actualizar_item_estado", methods=["POST"])
def api_actualizar_item_estado():
    try:
        data = request.get_json()
        item_id = data.get('item_id')
        nuevo_estado = data.get('estado')
        
        if not item_id or not nuevo_estado:
            return jsonify({"success": False, "message": "Faltan datos"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('UPDATE orden_items SET estado_item = %s WHERE id = %s', (nuevo_estado, item_id))
        conn.commit()
        
        socketio.emit('cambiar_estado_item_chef', {
            'item_id': item_id,
            'nuevo_estado': nuevo_estado
        }, namespace='/chef')
        
        return jsonify({"success": True, "message": "Estado actualizado"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

@app.route("/api/crear_orden", methods=["POST"])
@login_required
def api_crear_orden():
    try:
        data = request.get_json()
        mesa_id = data.get('mesa_id')
        mozo_nombre = data.get('mozo_nombre', 'Mozo')
        items = data.get('items', [])
        
        if not mesa_id or not items:
            return jsonify({"success": False, "message": "Datos incompletos"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Crear orden
        cur.execute('INSERT INTO ordenes (mesa_id, mozo_nombre) VALUES (%s, %s) RETURNING id', 
                   (mesa_id, mozo_nombre))
        orden_id = cur.fetchone()[0]
        
        # Agregar items
        for item in items:
            cur.execute('''
                INSERT INTO orden_items (orden_id, producto_id, producto_nombre, cantidad, precio_unitario)
                VALUES (%s, %s, %s, %s, %s)
            ''', (orden_id, item['producto_id'], item['producto_nombre'], item['cantidad'], item['precio_unitario']))
        
        # Actualizar mesa
        cur.execute('UPDATE mesas SET estado = %s WHERE id = %s', ('ocupada', mesa_id))
        
        conn.commit()
        
        # Notificar al chef
        socketio.emit('nuevo_pedido_chef', {
            'orden_id': orden_id,
            'mesa_id': mesa_id,
            'items_count': len(items)
        }, namespace='/chef')
        
        return jsonify({"success": True, "orden_id": orden_id})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

# ==============================
# LOGOUT
# ==============================
@app.route("/logout")
def logout():
    session.clear()
    flash('Sesión cerrada correctamente', 'info')
    return redirect(url_for('login'))

# ==============================
# MANEJO DE ERRORES
# ==============================
@app.errorhandler(404)
def pagina_no_encontrada(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def error_servidor(e):
    return render_template('500.html'), 500

# ==============================
# EJECUCIÓN PRINCIPAL
# ==============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        allow_unsafe_werkzeug=False,
        use_reloader=False
    )
