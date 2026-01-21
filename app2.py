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
    
    # Verificar si hay caja abierta
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, estado FROM caja_turnos WHERE estado = 'abierta' ORDER BY id DESC LIMIT 1")
        caja_abierta = cur.fetchone()
        cur.close()
        conn.close()
        
        if not caja_abierta:
            # Redirigir a página de caja sin turno
            return render_template("caja_sin_turno.html", 
                                 usuario=usuario_actual, 
                                 ahora=datetime.now(),
                                 mensaje="La caja está cerrada. Debes abrir un turno primero.")
    except Exception as e:
        print(f"Error verificando caja: {e}")
        return render_template("caja_sin_turno.html", 
                             usuario=usuario_actual, 
                             ahora=datetime.now(),
                             mensaje="Error al verificar estado de caja.")
    
    return render_template("caja.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/chef")
@login_required
def chef():
    usuario_actual = get_usuario_actual()
    if usuario_actual['rol'] != 'chef':
        flash('Acceso restringido para chefs', 'danger')
        return redirect(url_for('login'))
    return render_template("chef.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/panel_chef")
@login_required
def panel_chef():
    """Panel del chef - versión alternativa"""
    usuario_actual = get_usuario_actual()
    if usuario_actual['rol'] != 'chef':
        flash('Acceso restringido para chefs', 'danger')
        return redirect(url_for('login'))
    return render_template("panel_chef.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/ordenes")
@login_required
def ordenes():
    usuario_actual = get_usuario_actual()
    if usuario_actual['rol'] not in ['mozo', 'admin']:
        flash('Acceso restringido para mozos', 'danger')
        return redirect(url_for('login'))
    return render_template("ordenes.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/pedidos")
@login_required
def pedidos():
    """Panel de pedidos - para mozos"""
    usuario_actual = get_usuario_actual()
    if usuario_actual['rol'] not in ['mozo', 'admin']:
        flash('Acceso restringido para mozos', 'danger')
        return redirect(url_for('login'))
    return render_template("pedidos.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/productos")
@login_required
def productos():
    usuario_actual = get_usuario_actual()
    search = request.args.get('search', '')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if search:
        cur.execute('''
            SELECT p.id, p.nombre, p.precio, p.stock, p.tipo, p.codigo_barra,
                   c.nombre as categoria_nombre
            FROM productos p 
            LEFT JOIN categorias c ON p.categoria_id = c.id
            WHERE p.nombre ILIKE %s
            ORDER BY p.nombre
        ''', (f'%{search}%',))
    else:
        cur.execute('''
            SELECT p.id, p.nombre, p.precio, p.stock, p.tipo, p.codigo_barra,
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
            'codigo_barra': p[5] if p[5] else '',
            'categoria_nombre': p[6] if p[6] else 'Sin categoría'
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
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = '''
        SELECT o.id, m.numero as mesa_numero, o.mozo_nombre, o.total, 
               o.fecha_apertura, o.fecha_cierre, o.estado,
               COUNT(oi.id) as items_count
        FROM ordenes o 
        JOIN mesas m ON o.mesa_id = m.id 
        LEFT JOIN orden_items oi ON o.id = oi.orden_id
        WHERE o.estado = 'cerrada'
    '''
    
    params = []
    
    if fecha_inicio:
        query += ' AND DATE(o.fecha_apertura) >= %s'
        params.append(fecha_inicio)
    
    if fecha_fin:
        query += ' AND DATE(o.fecha_apertura) <= %s'
        params.append(fecha_fin)
    
    query += ' GROUP BY o.id, m.numero ORDER BY o.fecha_apertura DESC'
    
    cur.execute(query, params)
    ventas_db = cur.fetchall()
    
    total_ventas = sum(float(v[3]) if v[3] else 0 for v in ventas_db)
    total_ordenes = len(ventas_db)
    promedio_venta = total_ventas / total_ordenes if total_ordenes > 0 else 0
    
    ventas_list = []
    for v in ventas_db:
        ventas_list.append({
            'id': v[0],
            'mesa_numero': v[1],
            'mozo_nombre': v[2],
            'total': float(v[3]) if v[3] else 0,
            'fecha_apertura': v[4],
            'fecha_cierre': v[5],
            'estado': v[6],
            'items_count': v[7]
        })
    
    cur.close()
    conn.close()
    
    estadisticas = {
        'total_ordenes': total_ordenes,
        'total_ventas': total_ventas,
        'promedio_venta': promedio_venta
    }
    
    return render_template("ventas.html",
                         usuario=usuario_actual,
                         ventas=ventas_list,
                         estadisticas=estadisticas,
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin,
                         ahora=datetime.now())

@app.route("/historial_caja")
@login_required
def historial_caja():
    usuario_actual = get_usuario_actual()
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = '''
        SELECT id, fecha_apertura, fecha_cierre, monto_inicial, 
               monto_final_real, total_ventas, monto_esperado, 
               diferencia, observaciones, estado
        FROM caja_turnos
        WHERE 1=1
    '''
    
    params = []
    
    if fecha_inicio:
        query += ' AND DATE(fecha_apertura) >= %s'
        params.append(fecha_inicio)
    
    if fecha_fin:
        query += ' AND DATE(fecha_apertura) <= %s'
        params.append(fecha_fin)
    
    query += ' ORDER BY fecha_apertura DESC'
    
    cur.execute(query, params)
    turnos_db = cur.fetchall()
    
    turnos_list = []
    for t in turnos_db:
        turnos_list.append({
            'id': t[0],
            'fecha_apertura': t[1],
            'fecha_cierre': t[2],
            'monto_inicial': float(t[3]) if t[3] else 0,
            'monto_final_real': float(t[4]) if t[4] else 0,
            'total_ventas': float(t[5]) if t[5] else 0,
            'monto_esperado': float(t[6]) if t[6] else 0,
            'diferencia': float(t[7]) if t[7] else 0,
            'observaciones': t[8],
            'estado': t[9]
        })
    
    cur.close()
    conn.close()
    
    return render_template("historial_caja.html",
                         usuario=usuario_actual,
                         turnos=turnos_list,
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin,
                         ahora=datetime.now())

# ==============================
# RUTAS DE CREACIÓN/EDICIÓN
# ==============================
@app.route("/crear_producto", methods=["GET", "POST"])
@login_required
def crear_producto():
    usuario_actual = get_usuario_actual()
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, nombre FROM categorias ORDER BY nombre')
    categorias = [{'id': c[0], 'nombre': c[1]} for c in cur.fetchall()]
    cur.close()
    conn.close()
    
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        precio = request.form.get("precio", "0")
        stock = request.form.get("stock", "0")
        categoria_id = request.form.get("categoria_id")
        tipo = request.form.get("tipo", "producto")
        codigo_barra = request.form.get("codigo_barra", "")
        
        if not nombre or not precio:
            flash('Nombre y precio son requeridos', 'danger')
            return redirect(url_for('crear_producto'))
        
        try:
            precio_float = float(precio)
            stock_int = int(stock) if stock else 0
            
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO productos (nombre, precio, stock, categoria_id, tipo, codigo_barra) 
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (nombre, precio_float, stock_int, categoria_id, tipo, codigo_barra))
            
            conn.commit()
            flash(f'Producto "{nombre}" creado exitosamente', 'success')
            return redirect(url_for('productos'))
            
        except Exception as e:
            flash(f'Error al crear producto: {str(e)}', 'danger')
            return redirect(url_for('crear_producto'))
        finally:
            try:
                cur.close()
                conn.close()
            except:
                pass
    
    return render_template("crear_producto.html",
                         usuario=usuario_actual,
                         categorias=categorias,
                         ahora=datetime.now(),
                         tipos_producto=[
                             {'valor': 'producto', 'nombre': 'Producto General'},
                             {'valor': 'comida', 'nombre': 'Comida'},
                             {'valor': 'bebida', 'nombre': 'Bebida'}
                         ])

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
        finally:
            try:
                cur.close()
                conn.close()
            except:
                pass
    
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
        finally:
            try:
                cur.close()
                conn.close()
            except:
                pass
    
    return render_template("crear_categoria.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/crear_proveedor", methods=["GET", "POST"])
@login_required
def crear_proveedor():
    usuario_actual = get_usuario_actual()
    
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        contacto = request.form.get("contacto", "")
        telefono = request.form.get("telefono", "")
        email = request.form.get("email", "")
        direccion = request.form.get("direccion", "")
        
        if not nombre:
            flash('Nombre del proveedor requerido', 'danger')
            return redirect(url_for('crear_proveedor'))
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO proveedores (nombre, contacto, telefono, email, direccion) 
                VALUES (%s, %s, %s, %s, %s)
            ''', (nombre, contacto, telefono, email, direccion))
            conn.commit()
            flash(f'Proveedor "{nombre}" creado exitosamente', 'success')
            return redirect(url_for('proveedores'))
        except Exception as e:
            flash(f'Error al crear proveedor: {str(e)}', 'danger')
            return redirect(url_for('crear_proveedor'))
        finally:
            try:
                cur.close()
                conn.close()
            except:
                pass
    
    return render_template("crear_proveedor.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/abrir_caja", methods=["GET", "POST"])
@login_required
def abrir_caja():
    usuario_actual = get_usuario_actual()
    
    if request.method == "POST":
        monto_inicial = request.form.get("monto_inicial", 0)
        observaciones = request.form.get("observaciones", "")
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Verificar si ya hay caja abierta
            cur.execute("SELECT id FROM caja_turnos WHERE estado = 'abierta'")
            if cur.fetchone():
                flash('Ya hay una caja abierta', 'danger')
                return redirect(url_for('caja'))
            
            # Abrir nueva caja
            cur.execute('''
                INSERT INTO caja_turnos (fecha_apertura, monto_inicial, observaciones, estado)
                VALUES (NOW(), %s, %s, 'abierta')
            ''', (monto_inicial, observaciones))
            
            conn.commit()
            flash('Caja abierta exitosamente', 'success')
            return redirect(url_for('caja'))
            
        except Exception as e:
            flash(f'Error al abrir caja: {str(e)}', 'danger')
        finally:
            try:
                cur.close()
                conn.close()
            except:
                pass
    
    return render_template("abrir_caja.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/abrir_mesa/<int:mesa_id>")
@login_required
def abrir_mesa(mesa_id):
    """Abrir una mesa (cambiar estado a disponible)"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Verificar si la mesa existe
        cur.execute('SELECT * FROM mesas WHERE id = %s', (mesa_id,))
        mesa = cur.fetchone()
        
        if not mesa:
            flash('Mesa no encontrada', 'danger')
            return redirect(url_for('mesas'))
        
        # Cambiar estado a disponible
        cur.execute('UPDATE mesas SET estado = %s WHERE id = %s', ('disponible', mesa_id))
        
        # Verificar si hay órdenes abiertas en esta mesa
        cur.execute('SELECT id FROM ordenes WHERE mesa_id = %s AND estado IN (%s, %s, %s)', 
                   (mesa_id, 'abierta', 'proceso', 'listo'))
        orden_activa = cur.fetchone()
        
        if orden_activa:
            # Si hay orden activa, también cambiar estado de la orden
            cur.execute('UPDATE ordenes SET estado = %s WHERE id = %s', ('cerrada', orden_activa[0]))
        
        conn.commit()
        
        flash(f'Mesa #{mesa[1]} abierta exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        print(f"Error abriendo mesa: {e}")
        flash(f'Error al abrir mesa: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('mesas'))

@app.route("/cerrar_caja_form", methods=["GET", "POST"])
@login_required
def cerrar_caja_form():
    """Formulario para cerrar caja"""
    usuario_actual = get_usuario_actual()
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Obtener turno actual abierto
    cur.execute("SELECT * FROM caja_turnos WHERE estado = 'abierta' ORDER BY fecha_apertura DESC LIMIT 1")
    turno_db = cur.fetchone()
    
    if not turno_db:
        flash('No hay turno de caja abierto', 'warning')
        return redirect(url_for('caja'))
    
    turno = {
        'id': turno_db[0],
        'fecha_apertura': turno_db[1],
        'fecha_cierre': turno_db[2],
        'monto_inicial': float(turno_db[3]) if turno_db[3] else 0,
        'monto_final_real': float(turno_db[4]) if turno_db[4] else 0,
        'total_ventas': float(turno_db[5]) if turno_db[5] else 0,
        'monto_esperado': float(turno_db[6]) if turno_db[6] else 0,
        'diferencia': float(turno_db[7]) if turno_db[7] else 0,
        'observaciones': turno_db[8],
        'estado': turno_db[9]
    }
    
    # Calcular ventas durante el turno
    cur.execute('''
        SELECT COALESCE(SUM(total), 0) as total_ventas_turno
        FROM ordenes 
        WHERE fecha_apertura >= %s 
        AND estado = 'cerrada'
    ''', (turno['fecha_apertura'],))
    
    total_ventas_turno = cur.fetchone()[0] or 0
    
    if request.method == "POST":
        monto_final_real = request.form.get("monto_final_real", "0")
        observaciones = request.form.get("observaciones", "")
        
        try:
            monto_final_real_float = float(monto_final_real)
            monto_esperado = turno['monto_inicial'] + float(total_ventas_turno)
            diferencia = monto_final_real_float - monto_esperado
            
            # Actualizar turno
            cur.execute('''
                UPDATE caja_turnos 
                SET fecha_cierre = %s, 
                    monto_final_real = %s,
                    total_ventas = %s,
                    monto_esperado = %s,
                    diferencia = %s,
                    observaciones = %s,
                    estado = 'cerrada'
                WHERE id = %s
            ''', (datetime.now(), monto_final_real_float, total_ventas_turno, 
                  monto_esperado, diferencia, observaciones, turno['id']))
            
            # Crear registro en cierres_caja
            cur.execute('''
                INSERT INTO cierres_caja 
                (turno_id, fecha_cierre, monto_total, observaciones, usuario_cierre)
                VALUES (%s, %s, %s, %s, %s)
            ''', (turno['id'], datetime.now(), monto_final_real_float, 
                  observaciones, usuario_actual['nombre']))
            
            conn.commit()
            flash('Turno de caja cerrado exitosamente', 'success')
            return redirect(url_for('caja'))
            
        except Exception as e:
            conn.rollback()
            flash(f'Error al cerrar caja: {str(e)}', 'danger')
            return redirect(url_for('cerrar_caja_form'))
        finally:
            cur.close()
            conn.close()
    
    cur.close()
    conn.close()
    
    return render_template("cerrar_caja_form.html",
                         usuario=usuario_actual,
                         turno=turno,
                         total_ventas_turno=total_ventas_turno,
                         monto_esperado=turno['monto_inicial'] + float(total_ventas_turno),
                         ahora=datetime.now())

@app.route("/cierre_caja_completo")
@login_required
def cierre_caja_completo():
    """Página de confirmación de cierre de caja"""
    usuario_actual = get_usuario_actual()
    return render_template("cierre_caja_completo.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/confirmacion_apertura")
@login_required
def confirmacion_apertura():
    """Confirmación de apertura de caja"""
    usuario_actual = get_usuario_actual()
    return render_template("confirmacion_apertura.html", usuario=usuario_actual, ahora=datetime.now())

# ==============================
# RUTAS DE EDICIÓN
# ==============================
@app.route("/editar_producto/<int:id>", methods=["GET", "POST"])
@login_required
def editar_producto(id):
    usuario_actual = get_usuario_actual()
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "GET":
        cur.execute('SELECT p.*, c.nombre as categoria_nombre FROM productos p LEFT JOIN categorias c ON p.categoria_id = c.id WHERE p.id = %s', (id,))
        producto_db = cur.fetchone()
        
        if not producto_db:
            cur.close()
            conn.close()
            flash('Producto no encontrado', 'danger')
            return redirect(url_for('productos'))
        
        producto = {
            'id': producto_db[0],
            'codigo_barra': producto_db[1],
            'nombre': producto_db[2],
            'precio': float(producto_db[3]) if producto_db[3] else 0,
            'stock': producto_db[4],
            'categoria_id': producto_db[5],
            'proveedor_id': producto_db[6],
            'tipo': producto_db[7],
            'categoria_nombre': producto_db[9]
        }
        
        cur.execute('SELECT id, nombre FROM categorias ORDER BY nombre')
        categorias = cur.fetchall()
        
        cur.close()
        conn.close()
        
        categorias_list = [{'id': c[0], 'nombre': c[1]} for c in categorias]
        
        return render_template("editar_producto.html",
                             usuario=usuario_actual,
                             producto=producto,
                             categorias=categorias_list,
                             ahora=datetime.now())
    
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        precio = request.form.get("precio", "0")
        stock = request.form.get("stock", "0")
        categoria_id = request.form.get("categoria_id")
        tipo = request.form.get("tipo", "producto")
        codigo_barra = request.form.get("codigo_barra", "")
        
        if not nombre or not precio:
            flash('Nombre y precio son requeridos', 'danger')
            return redirect(url_for('editar_producto', id=id))
        
        try:
            precio_float = float(precio)
            stock_int = int(stock) if stock else 0
            
            cur.execute('''
                UPDATE productos 
                SET nombre = %s, precio = %s, stock = %s, categoria_id = %s, tipo = %s, codigo_barra = %s
                WHERE id = %s
            ''', (nombre, precio_float, stock_int, categoria_id, tipo, codigo_barra, id))
            
            conn.commit()
            flash(f'Producto "{nombre}" actualizado exitosamente', 'success')
            return redirect(url_for('productos'))
            
        except Exception as e:
            flash(f'Error al actualizar producto: {str(e)}', 'danger')
            return redirect(url_for('editar_producto', id=id))
        finally:
            cur.close()
            conn.close()

@app.route("/editar_mesa/<int:id>", methods=["GET", "POST"])
@login_required
def editar_mesa(id):
    usuario_actual = get_usuario_actual()
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "GET":
        cur.execute('SELECT * FROM mesas WHERE id = %s', (id,))
        mesa_db = cur.fetchone()
        
        if not mesa_db:
            cur.close()
            conn.close()
            flash('Mesa no encontrada', 'danger')
            return redirect(url_for('mesas'))
        
        mesa = {
            'id': mesa_db[0],
            'numero': mesa_db[1],
            'capacidad': mesa_db[2],
            'estado': mesa_db[3],
            'ubicacion': mesa_db[4]
        }
        
        cur.close()
        conn.close()
        
        return render_template("editar_mesa.html",
                             usuario=usuario_actual,
                             mesa=mesa,
                             ahora=datetime.now())
    
    if request.method == "POST":
        numero = request.form.get("numero")
        capacidad = request.form.get("capacidad", 4)
        ubicacion = request.form.get("ubicacion", "")
        estado = request.form.get("estado", "disponible")
        
        if not numero:
            flash('Número de mesa requerido', 'danger')
            return redirect(url_for('editar_mesa', id=id))
        
        try:
            cur.execute('''
                UPDATE mesas 
                SET numero = %s, capacidad = %s, ubicacion = %s, estado = %s
                WHERE id = %s
            ''', (numero, capacidad, ubicacion, estado, id))
            
            conn.commit()
            flash(f'Mesa #{numero} actualizada exitosamente', 'success')
            return redirect(url_for('mesas'))
            
        except Exception as e:
            flash(f'Error al actualizar mesa: {str(e)}', 'danger')
            return redirect(url_for('editar_mesa', id=id))
        finally:
            cur.close()
            conn.close()

@app.route("/editar_categoria/<int:id>", methods=["GET", "POST"])
@login_required
def editar_categoria(id):
    usuario_actual = get_usuario_actual()
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "GET":
        cur.execute('SELECT * FROM categorias WHERE id = %s', (id,))
        categoria_db = cur.fetchone()
        
        if not categoria_db:
            cur.close()
            conn.close()
            flash('Categoría no encontrada', 'danger')
            return redirect(url_for('categorias'))
        
        categoria = {
            'id': categoria_db[0],
            'nombre': categoria_db[1]
        }
        
        cur.close()
        conn.close()
        
        return render_template("editar_categoria.html",
                             usuario=usuario_actual,
                             categoria=categoria,
                             ahora=datetime.now())
    
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        
        if not nombre:
            flash('Nombre de categoría requerido', 'danger')
            return redirect(url_for('editar_categoria', id=id))
        
        try:
            cur.execute('UPDATE categorias SET nombre = %s WHERE id = %s', (nombre, id))
            conn.commit()
            flash(f'Categoría "{nombre}" actualizada exitosamente', 'success')
            return redirect(url_for('categorias'))
            
        except Exception as e:
            flash(f'Error al actualizar categoría: {str(e)}', 'danger')
            return redirect(url_for('editar_categoria', id=id))
        finally:
            cur.close()
            conn.close()

@app.route("/editar_proveedor/<int:id>", methods=["GET", "POST"])
@login_required
def editar_proveedor(id):
    usuario_actual = get_usuario_actual()
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "GET":
        cur.execute('SELECT * FROM proveedores WHERE id = %s', (id,))
        proveedor_db = cur.fetchone()
        
        if not proveedor_db:
            cur.close()
            conn.close()
            flash('Proveedor no encontrado', 'danger')
            return redirect(url_for('proveedores'))
        
        proveedor = {
            'id': proveedor_db[0],
            'nombre': proveedor_db[1],
            'contacto': proveedor_db[2],
            'telefono': proveedor_db[3],
            'email': proveedor_db[4],
            'direccion': proveedor_db[5],
            'activo': proveedor_db[6]
        }
        
        cur.close()
        conn.close()
        
        return render_template("editar_proveedor.html",
                             usuario=usuario_actual,
                             proveedor=proveedor,
                             ahora=datetime.now())
    
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        contacto = request.form.get("contacto", "").strip()
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip()
        direccion = request.form.get("direccion", "").strip()
        activo = request.form.get("activo", "on") == "on"
        
        if not nombre:
            flash('Nombre de proveedor requerido', 'danger')
            return redirect(url_for('editar_proveedor', id=id))
        
        try:
            cur.execute('''
                UPDATE proveedores 
                SET nombre = %s, contacto = %s, telefono = %s, 
                    email = %s, direccion = %s, activo = %s
                WHERE id = %s
            ''', (nombre, contacto, telefono, email, direccion, activo, id))
            
            conn.commit()
            flash(f'Proveedor "{nombre}" actualizado exitosamente', 'success')
            return redirect(url_for('proveedores'))
            
        except Exception as e:
            flash(f'Error al actualizar proveedor: {str(e)}', 'danger')
            return redirect(url_for('editar_proveedor', id=id))
        finally:
            cur.close()
            conn.close()

@app.route("/editar_pedido/<int:id>", methods=["GET", "POST"])
@login_required
def editar_pedido(id):
    usuario_actual = get_usuario_actual()
    return render_template("editar_pedido.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/crear_pedido", methods=["GET", "POST"])
@login_required
def crear_pedido():
    usuario_actual = get_usuario_actual()
    if usuario_actual['rol'] not in ['mozo', 'admin']:
        flash('Acceso restringido para mozos', 'danger')
        return redirect(url_for('login'))
    return render_template("crear_pedido.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/ver_pedido/<int:pedido_id>")
@login_required
def ver_pedido(pedido_id):
    usuario_actual = get_usuario_actual()
    return render_template("ver_pedido.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/pago_pedido/<int:pedido_id>")
@login_required
def pago_pedido(pedido_id):
    usuario_actual = get_usuario_actual()
    return render_template("pago_pedido.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/detalle_venta/<int:venta_id>")
@login_required
def detalle_venta(venta_id):
    usuario_actual = get_usuario_actual()
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Obtener información de la venta
        cur.execute('''
            SELECT o.*, m.numero as mesa_numero 
            FROM ordenes o 
            JOIN mesas m ON o.mesa_id = m.id 
            WHERE o.id = %s
        ''', (venta_id,))
        venta_db = cur.fetchone()
        
        if not venta_db:
            flash('Venta no encontrada', 'danger')
            return redirect(url_for('ventas'))
        
        venta = {
            'id': venta_db[0],
            'mesa_id': venta_db[1],
            'mesa_numero': venta_db[9],
            'mozo_nombre': venta_db[2],
            'estado': venta_db[3],
            'observaciones': venta_db[4],
            'total': float(venta_db[5]) if venta_db[5] else 0,
            'fecha_apertura': venta_db[6],
            'fecha_cierre': venta_db[7]
        }
        
        # Obtener items de la venta
        cur.execute('SELECT * FROM orden_items WHERE orden_id = %s ORDER BY id', (venta_id,))
        items_db = cur.fetchall()
        
        items = []
        for item in items_db:
            items.append({
                'id': item[0],
                'producto_nombre': item[3],
                'cantidad': item[4],
                'precio_unitario': float(item[5]) if item[5] else 0,
                'observaciones': item[6],
                'estado_item': item[7]
            })
        
        cur.close()
        conn.close()
        
        return render_template("detalle_venta.html",
                             usuario=usuario_actual,
                             venta=venta,
                             items=items,
                             ahora=datetime.now())
        
    except Exception as e:
        print(f"Error obteniendo detalle de venta: {e}")
        flash('Error al obtener detalle de venta', 'danger')
        return redirect(url_for('ventas'))

# ==============================
# ELIMINACIÓN DE REGISTROS
# ==============================
@app.route("/eliminar_producto/<int:id>")
@login_required
def eliminar_producto(id):
    """Eliminar producto"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Verificar si hay órdenes activas con este producto
        cur.execute('''
            SELECT COUNT(*) FROM orden_items oi
            JOIN ordenes o ON oi.orden_id = o.id
            WHERE oi.producto_id = %s AND o.estado IN ('abierta', 'proceso')
        ''', (id,))
        
        conteo = cur.fetchone()[0]
        
        if conteo > 0:
            flash('No se puede eliminar, el producto está en órdenes activas', 'danger')
            return redirect(url_for('productos'))
        
        # Obtener nombre del producto
        cur.execute('SELECT nombre FROM productos WHERE id = %s', (id,))
        producto_nombre = cur.fetchone()
        nombre = producto_nombre[0] if producto_nombre else f'ID {id}'
        
        # Eliminar el producto
        cur.execute('DELETE FROM productos WHERE id = %s', (id,))
        conn.commit()
        
        flash(f'Producto "{nombre}" eliminado exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        print(f"Error eliminando producto: {e}")
        flash(f'Error al eliminar producto: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('productos'))

@app.route("/eliminar_mesa/<int:id>")
@login_required
def eliminar_mesa(id):
    """Eliminar mesa"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Verificar si hay órdenes activas en la mesa
        cur.execute('SELECT COUNT(*) FROM ordenes WHERE mesa_id = %s AND estado IN (%s, %s, %s)', 
                   (id, 'abierta', 'proceso', 'listo'))
        
        conteo = cur.fetchone()[0]
        
        if conteo > 0:
            flash('No se puede eliminar, la mesa tiene órdenes activas', 'danger')
            return redirect(url_for('mesas'))
        
        cur.execute('SELECT numero FROM mesas WHERE id = %s', (id,))
        mesa_numero = cur.fetchone()
        numero = mesa_numero[0] if mesa_numero else f'ID {id}'
        
        cur.execute('DELETE FROM mesas WHERE id = %s', (id,))
        conn.commit()
        
        flash(f'Mesa #{numero} eliminada exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        print(f"Error eliminando mesa: {e}")
        flash(f'Error al eliminar mesa: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('mesas'))

@app.route("/eliminar_categoria/<int:id>")
@login_required
def eliminar_categoria(id):
    """Eliminar categoría"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Verificar si hay productos usando esta categoría
        cur.execute('SELECT COUNT(*) FROM productos WHERE categoria_id = %s', (id,))
        conteo = cur.fetchone()[0]
        
        if conteo > 0:
            flash('No se puede eliminar, hay productos usando esta categoría', 'danger')
            return redirect(url_for('categorias'))
        
        cur.execute('SELECT nombre FROM categorias WHERE id = %s', (id,))
        categoria_nombre = cur.fetchone()
        nombre = categoria_nombre[0] if categoria_nombre else f'ID {id}'
        
        cur.execute('DELETE FROM categorias WHERE id = %s', (id,))
        conn.commit()
        
        flash(f'Categoría "{nombre}" eliminada exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        print(f"Error eliminando categoría: {e}")
        flash(f'Error al eliminar categoría: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('categorias'))

@app.route("/eliminar_proveedor/<int:id>")
@login_required
def eliminar_proveedor(id):
    """Eliminar proveedor"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Verificar si hay productos usando este proveedor
        cur.execute('SELECT COUNT(*) FROM productos WHERE proveedor_id = %s', (id,))
        conteo = cur.fetchone()[0]
        
        if conteo > 0:
            flash('No se puede eliminar, hay productos usando este proveedor', 'danger')
            return redirect(url_for('proveedores'))
        
        cur.execute('SELECT nombre FROM proveedores WHERE id = %s', (id,))
        proveedor_nombre = cur.fetchone()
        nombre = proveedor_nombre[0] if proveedor_nombre else f'ID {id}'
        
        cur.execute('DELETE FROM proveedores WHERE id = %s', (id,))
        conn.commit()
        
        flash(f'Proveedor "{nombre}" eliminado exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        print(f"Error eliminando proveedor: {e}")
        flash(f'Error al eliminar proveedor: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('proveedores'))

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

@app.route("/api/ordenes_activas")
def api_ordenes_activas():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT o.id, o.mesa_id, m.numero as mesa_numero, o.mozo_nombre, 
                   o.total, o.fecha_apertura, o.estado, COUNT(oi.id) as items_count 
            FROM ordenes o 
            JOIN mesas m ON o.mesa_id = m.id 
            LEFT JOIN orden_items oi ON o.id = oi.orden_id 
            WHERE o.estado IN ('abierta', 'proceso', 'listo') 
            GROUP BY o.id, m.numero 
            ORDER BY o.fecha_apertura DESC
        ''')
        ordenes_db = cur.fetchall()
        ordenes_list = []
        for o in ordenes_db:
            ordenes_list.append({
                'id': o[0], 'mesa_id': o[1], 'mesa_numero': o[2],
                'mozo_nombre': o[3], 'total': float(o[4]) if o[4] else 0,
                'fecha_apertura': o[5].strftime('%Y-%m-%d %H:%M:%S') if o[5] else '',
                'estado': o[6], 'items_count': o[7]
            })
        return jsonify(ordenes_list)
    except Exception as e:
        print(f"Error obteniendo órdenes activas: {e}")
        return jsonify([])
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

@app.route("/api/cerrar_orden/<int:orden_id>", methods=["POST"])
@login_required
def api_cerrar_orden(orden_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Obtener información de la orden
        cur.execute('SELECT mesa_id, total FROM ordenes WHERE id = %s', (orden_id,))
        orden_info = cur.fetchone()
        
        if not orden_info:
            return jsonify({"success": False, "message": "Orden no encontrada"}), 404
        
        mesa_id = orden_info[0]
        total = orden_info[1]
        
        # Actualizar orden a cerrada
        cur.execute('UPDATE ordenes SET estado = %s, fecha_cierre = %s WHERE id = %s', 
                   ('cerrada', datetime.now(), orden_id))
        
        # Liberar mesa
        cur.execute('UPDATE mesas SET estado = %s WHERE id = %s', ('disponible', mesa_id))
        
        # Actualizar ventas en turno activo
        cur.execute('''
            UPDATE caja_turnos 
            SET total_ventas = COALESCE(total_ventas, 0) + %s
            WHERE estado = 'abierta'
        ''', (total,))
        
        conn.commit()
        
        return jsonify({"success": True, "message": "Orden cerrada exitosamente"})
        
    except Exception as e:
        conn.rollback()
        print(f"Error cerrando orden: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route("/api/abrir_turno", methods=["POST"])
@login_required
def api_abrir_turno():
    try:
        data = request.get_json()
        monto_inicial = data.get('monto_inicial', 0)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar si ya hay un turno abierto
        cur.execute("SELECT COUNT(*) FROM caja_turnos WHERE estado = 'abierta'")
        turnos_abiertos = cur.fetchone()[0]
        
        if turnos_abiertos > 0:
            return jsonify({"success": False, "message": "Ya hay un turno abierto"}), 400
        
        try:
            cur.execute('''
                INSERT INTO caja_turnos (fecha_apertura, monto_inicial)
                VALUES (%s, %s) RETURNING id
            ''', (datetime.now(), monto_inicial))
            
            turno_id = cur.fetchone()[0]
            conn.commit()
            
            return jsonify({"success": True, "turno_id": turno_id, "message": "Turno abierto exitosamente"})
            
        except Exception as e:
            conn.rollback()
            return jsonify({"success": False, "message": str(e)}), 500
        finally:
            cur.close()
            conn.close()
            
    except Exception as e:
        print(f"Error en api_abrir_turno: {e}")
        return jsonify({"success": False, "message": "Error del servidor"}), 500

@app.route("/api/notificaciones_mozo")
def api_notificaciones_mozo():
    """API pública para notificaciones"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cinco_minutos_atras = datetime.now() - timedelta(minutes=5)
        
        cur.execute('''
            SELECT DISTINCT o.id, m.numero as mesa_numero, o.estado as estado_orden, 
                   COUNT(CASE WHEN oi.estado_item = %s AND oi.tiempo_fin >= %s THEN 1 END) as items_nuevos 
            FROM ordenes o 
            JOIN mesas m ON o.mesa_id = m.id 
            JOIN orden_items oi ON o.id = oi.orden_id 
            WHERE o.estado IN (%s, %s, %s) 
            GROUP BY o.id, m.numero, o.estado 
            HAVING COUNT(CASE WHEN oi.estado_item = %s AND oi.tiempo_fin >= %s THEN 1 END) > 0 
            ORDER BY o.id DESC
        ''', ('listo', cinco_minutos_atras, 'abierta', 'proceso', 'listo', 'listo', cinco_minutos_atras))
        
        notificaciones_db = cur.fetchall()
        notificaciones_list = []
        
        for notif in notificaciones_db:
            notificaciones_list.append({
                'orden_id': notif[0], 
                'mesa_numero': notif[1], 
                'estado_orden': notif[2],
                'items_nuevos': notif[3], 
                'mensaje': f"Mesa {notif[1]} - {notif[3]} item(s) listo(s)"
            })
        
        return jsonify(notificaciones_list)
        
    except Exception as e:
        print(f"Error obteniendo notificaciones: {e}")
        return jsonify([])
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
# TEMPLATES DE ERROR
# ==============================
@app.errorhandler(404)
def pagina_no_encontrada(e):
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Página no encontrada</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            h1 { color: #e74c3c; }
            a { color: #3498db; text-decoration: none; }
        </style>
    </head>
    <body>
        <h1>404 - Página no encontrada</h1>
        <p>La página que buscas no existe.</p>
        <a href="/">Volver al inicio</a>
    </body>
    </html>
    ''', 404

@app.errorhandler(500)
def error_servidor(e):
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Error del servidor</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            h1 { color: #e74c3c; }
            a { color: #3498db; text-decoration: none; }
        </style>
    </head>
    <body>
        <h1>500 - Error interno del servidor</h1>
        <p>Algo salió mal en el servidor.</p>
        <a href="/">Volver al inicio</a>
    </body>
    </html>
    ''', 500

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
