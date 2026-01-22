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

def abrir_caja_automaticamente():
    """Función para abrir caja automáticamente si no hay una abierta"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar si ya hay caja abierta
        cur.execute("SELECT id FROM caja_turnos WHERE estado = 'abierta'")
        if cur.fetchone():
            print("✅ Ya hay una caja abierta")
            cur.close()
            conn.close()
            return True
        
        # Abrir nueva caja automáticamente
        print("🔓 Abriendo caja automáticamente...")
        cur.execute('''
            INSERT INTO caja_turnos (fecha_apertura, monto_inicial, observaciones, estado)
            VALUES (NOW(), 0, 'Caja abierta automáticamente al iniciar sesión', 'abierta')
            RETURNING id
        ''')
        caja_id = cur.fetchone()[0]
        conn.commit()
        print(f"✅ Caja #{caja_id} abierta automáticamente")
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error al abrir caja automáticamente: {e}")
        return False

# ==============================
# RUTAS PRINCIPALES (MEJORADA)
# ==============================
@app.route("/")
def index():
    """Página principal - Redirige a login"""
    return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    """Página de login con apertura automática de caja"""
    if 'user_id' in session:
        usuario_actual = get_usuario_actual()
        if usuario_actual:
            # Redirigir según rol
            if usuario_actual['rol'] == 'chef':
                return redirect(url_for('chef'))
            elif usuario_actual['rol'] == 'mozo':
                return redirect(url_for('ordenes'))
            else:
                # Para admin y cajero: abrir caja automáticamente y redirigir a caja
                abrir_caja_automaticamente()
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
            
            # Redirigir según rol
            if usuario['rol'] == 'chef':
                return redirect(url_for('chef'))
            elif usuario['rol'] == 'mozo':
                return redirect(url_for('ordenes'))
            else:
                # Para admin y cajero: abrir caja automáticamente
                if abrir_caja_automaticamente():
                    flash('Turno de caja abierto automáticamente con monto inicial $0', 'info')
                return redirect(url_for('caja'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    
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
# PANEL DE CAJA (VERSIÓN DEFINITIVA - SIN MENSAJES DE CAJA CERRADA)
# ==============================
@app.route("/caja")
@login_required
def caja():
    """Panel de caja - Versión definitiva con apertura automática silenciosa"""
    usuario_actual = get_usuario_actual()
    
    # Si el usuario no es cajero o admin, redirigir
    if usuario_actual['rol'] not in ['cajero', 'admin']:
        flash('Acceso restringido. Solo cajeros y administradores pueden acceder a la caja.', 'warning')
        return redirect(url_for('productos'))
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar si hay caja abierta
        cur.execute("SELECT id, fecha_apertura, monto_inicial FROM caja_turnos WHERE estado = 'abierta' ORDER BY id DESC LIMIT 1")
        caja_abierta = cur.fetchone()
        
        # ✅ NUNCA MOSTRAR MENSAJE DE CAJA CERRADA - SIEMPRE ABRIRLA
        if not caja_abierta:
            print(f"🔓 Abriendo caja automáticamente para {usuario_actual['nombre']}...")
            
            # Abrir caja automáticamente
            cur.execute('''
                INSERT INTO caja_turnos (fecha_apertura, monto_inicial, observaciones, estado)
                VALUES (NOW(), 0, 'Caja abierta automáticamente', 'abierta')
                RETURNING id
            ''')
            caja_id = cur.fetchone()[0]
            conn.commit()
            print(f"✅ Caja #{caja_id} abierta automáticamente")
            
            # Obtener la caja recién abierta
            cur.execute("SELECT id, fecha_apertura, monto_inicial FROM caja_turnos WHERE id = %s", (caja_id,))
            caja_abierta = cur.fetchone()
        
        # Crear diccionario con información de la caja
        caja_info = {
            'id': caja_abierta[0],
            'fecha_apertura': caja_abierta[1],
            'monto_inicial': float(caja_abierta[2]) if caja_abierta[2] else 0
        }
        
        # Obtener órdenes abiertas
        cur.execute('''
            SELECT o.id, m.numero as mesa_numero, o.mozo_nombre, o.total 
            FROM ordenes o 
            JOIN mesas m ON o.mesa_id = m.id 
            WHERE o.estado = 'abierta' 
            ORDER BY o.fecha_apertura DESC
        ''')
        ordenes_abiertas_db = cur.fetchall()
        
        ordenes_abiertas = []
        for o in ordenes_abiertas_db:
            ordenes_abiertas.append({
                'id': o[0],
                'mesa_numero': o[1],
                'mozo_nombre': o[2],
                'total': float(o[3]) if o[3] else 0
            })
        
        cur.close()
        conn.close()
        
        # ✅ SIEMPRE mostrar la caja abierta
        return render_template("caja.html", 
                             usuario=usuario_actual, 
                             ahora=datetime.now(),
                             turno_abierto=caja_info,
                             ordenes_abiertas=ordenes_abiertas)
        
    except Exception as e:
        print(f"❌ Error crítico en panel de caja: {e}")
        # En caso de error grave, redirigir a login
        flash('Error del sistema. Por favor, reinicia sesión.', 'danger')
        return redirect(url_for('logout'))

# ==============================
# PANELES PARA OTROS ROLES
# ==============================
@app.route("/chef")
@login_required
def chef():
    usuario_actual = get_usuario_actual()
    if usuario_actual['rol'] != 'chef':
        flash('Acceso restringido para chefs', 'warning')
        return redirect(url_for('login'))
    return render_template("chef.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/panel_chef")
@login_required
def panel_chef():
    """Panel del chef - versión alternativa"""
    usuario_actual = get_usuario_actual()
    if usuario_actual['rol'] != 'chef':
        flash('Acceso restringido para chefs', 'warning')
        return redirect(url_for('login'))
    return render_template("panel_chef.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/ordenes")
@login_required
def ordenes():
    usuario_actual = get_usuario_actual()
    if usuario_actual['rol'] not in ['mozo', 'admin']:
        flash('Acceso restringido para mozos', 'warning')
        return redirect(url_for('login'))
    return render_template("ordenes.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/pedidos")
@login_required
def pedidos():
    """Panel de pedidos - para mozos"""
    usuario_actual = get_usuario_actual()
    if usuario_actual['rol'] not in ['mozo', 'admin']:
        flash('Acceso restringido para mozos', 'warning')
        return redirect(url_for('login'))
    return render_template("pedidos.html", usuario=usuario_actual, ahora=datetime.now())

# ==============================
# RUTAS DE GESTIÓN (MANTENIDAS IGUAL)
# ==============================
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

# ==============================
# RUTAS DE CREACIÓN/EDICIÓN (MANTENIDAS IGUAL)
# ==============================
@app.route("/crear_producto", methods=["GET", "POST"])
@login_required
def crear_producto():
    usuario_actual = get_usuario_actual()
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, nombre FROM categorias ORDER BY nombre')
    categorias = [{'id': c[0], 'nombre': c[1]} for c in cur.fetchall()]
    
    cur.execute('SELECT id, nombre FROM proveedores WHERE activo = true ORDER BY nombre')
    proveedores = [{'id': p[0], 'nombre': p[1]} for p in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    # Definir tipos de producto
    tipos_producto = [
        {'valor': 'producto', 'nombre': 'Producto General'},
        {'valor': 'comida', 'nombre': 'Comida'},
        {'valor': 'bebida', 'nombre': 'Bebida'}
    ]
    
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        precio = request.form.get("precio", "0")
        stock = request.form.get("stock", "0")
        categoria_id = request.form.get("categoria_id")
        proveedor_id = request.form.get("proveedor_id")
        tipo = request.form.get("tipo", "producto")
        codigo_barra = request.form.get("codigo_barra", "")
        
        if not nombre or not precio:
            flash('Nombre y precio son requeridos', 'danger')
            return redirect(url_for('crear_producto'))
        
        try:
            precio_float = float(precio)
            
            # Manejar stock según tipo
            if tipo == 'comida':
                stock_int = None  # Para comidas, stock es NULL
                # Si no hay código de barras, generar uno
                if not codigo_barra:
                    codigo_barra = f"COM{datetime.now().strftime('%Y%m%d%H%M%S')}"
            else:
                # Para productos y bebidas, stock es requerido
                try:
                    stock_int = int(stock) if stock else 0
                except ValueError:
                    stock_int = 0
                
                # Código de barras requerido para productos y bebidas
                if not codigo_barra and tipo != 'comida':
                    codigo_barra = f"PROD{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO productos (nombre, precio, stock, categoria_id, proveedor_id, tipo, codigo_barra) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (nombre, precio_float, stock_int, categoria_id, proveedor_id, tipo, codigo_barra))
            
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
                         proveedores=proveedores,
                         tipos_producto=tipos_producto,
                         ahora=datetime.now())

# ==============================
# ABRIR CAJA MANUALMENTE (MEJORADA)
# ==============================
@app.route("/abrir_caja", methods=["GET", "POST"])
@login_required
def abrir_caja():
    """Formulario para abrir caja manualmente"""
    usuario_actual = get_usuario_actual()
    
    # Solo cajeros y admins pueden abrir caja
    if usuario_actual['rol'] not in ['cajero', 'admin']:
        flash('Solo cajeros y administradores pueden abrir caja', 'warning')
        return redirect(url_for('caja'))
    
    if request.method == "POST":
        monto_inicial = request.form.get("monto_inicial", 0)
        observaciones = request.form.get("observaciones", "")
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Verificar si ya hay caja abierta
            cur.execute("SELECT id FROM caja_turnos WHERE estado = 'abierta'")
            if cur.fetchone():
                flash('Ya hay una caja abierta. No puedes abrir otra.', 'warning')
                return redirect(url_for('caja'))
            
            # Abrir nueva caja
            cur.execute('''
                INSERT INTO caja_turnos (fecha_apertura, monto_inicial, observaciones, estado)
                VALUES (NOW(), %s, %s, 'abierta')
            ''', (monto_inicial, observaciones))
            
            conn.commit()
            flash(f'Caja abierta exitosamente con monto inicial ${float(monto_inicial):,.2f}', 'success')
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

# ==============================
# API MEJORADA PARA VERIFICAR CAJA
# ==============================
@app.route("/api/verificar_caja")
@login_required
def api_verificar_caja():
    """API para verificar estado de caja desde el frontend"""
    try:
        usuario_actual = get_usuario_actual()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar si hay caja abierta
        cur.execute("SELECT id, fecha_apertura, monto_inicial FROM caja_turnos WHERE estado = 'abierta' ORDER BY id DESC LIMIT 1")
        caja_abierta = cur.fetchone()
        
        if caja_abierta:
            response = {
                'abierta': True,
                'id': caja_abierta[0],
                'fecha_apertura': caja_abierta[1].strftime('%Y-%m-%d %H:%M:%S') if caja_abierta[1] else '',
                'monto_inicial': float(caja_abierta[2]) if caja_abierta[2] else 0,
                'mensaje': 'Caja abierta correctamente'
            }
        else:
            response = {
                'abierta': False,
                'mensaje': 'No hay caja abierta',
                'puede_abrir': usuario_actual['rol'] in ['cajero', 'admin']
            }
        
        cur.close()
        conn.close()
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error verificando caja: {e}")
        return jsonify({'abierta': False, 'error': str(e)})

# ==============================
# API PARA ABRIR CAJA DE EMERGENCIA (MEJORADA)
# ==============================
@app.route("/api/abrir_caja_emergencia", methods=["POST"])
@login_required
def api_abrir_caja_emergencia():
    """API para abrir caja de emergencia desde el frontend"""
    try:
        usuario_actual = get_usuario_actual()
        
        # Solo cajeros y admins pueden abrir caja
        if usuario_actual['rol'] not in ['cajero', 'admin']:
            return jsonify({
                "success": False, 
                "message": "Acceso restringido. Solo cajeros y administradores pueden abrir caja.",
                "redirect": "/login"
            }), 403
        
        # Intentar abrir caja automáticamente
        if abrir_caja_automaticamente():
            return jsonify({
                "success": True, 
                "message": "Caja abierta exitosamente con monto inicial $0",
                "redirect": "/caja"
            })
        else:
            return jsonify({
                "success": False, 
                "message": "Error al abrir caja automáticamente. Intenta abrirla manualmente.",
                "redirect": "/abrir_caja"
            }), 500
            
    except Exception as e:
        print(f"Error en api_abrir_caja_emergencia: {e}")
        return jsonify({
            "success": False, 
            "message": "Error del servidor",
            "redirect": "/caja"
        }), 500

# ==============================
# LOGOUT (MEJORADO)
# ==============================
@app.route("/logout")
def logout():
    """Cerrar sesión con mensaje informativo"""
    nombre = session.get('nombre', 'Usuario')
    session.clear()
    flash(f'Sesión cerrada correctamente. ¡Hasta pronto {nombre}!', 'info')
    return redirect(url_for('login'))

# ==============================
# RUTA DE BIENVENIDA
# ==============================
@app.route("/bienvenida")
@login_required
def bienvenida():
    """Página de bienvenida después del login"""
    usuario_actual = get_usuario_actual()
    
    # Verificar estado de caja para usuarios relevantes
    tiene_caja_abierta = False
    if usuario_actual['rol'] in ['cajero', 'admin']:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT id FROM caja_turnos WHERE estado = 'abierta'")
            tiene_caja_abierta = cur.fetchone() is not None
            cur.close()
            conn.close()
        except:
            pass
    
    return render_template("bienvenida.html",
                         usuario=usuario_actual,
                         tiene_caja_abierta=tiene_caja_abierta,
                         ahora=datetime.now())

# ==============================
# TEMPLATES DE ERROR (MEJORADOS)
# ==============================
@app.errorhandler(404)
def pagina_no_encontrada(e):
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Página no encontrada</title>
        <style>
            body { 
                font-family: 'Arial', sans-serif; 
                text-align: center; 
                padding: 50px; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
            }
            .error-container { 
                background: rgba(255, 255, 255, 0.1); 
                padding: 40px; 
                border-radius: 15px;
                backdrop-filter: blur(10px);
                max-width: 600px;
            }
            h1 { 
                font-size: 3em; 
                margin-bottom: 20px;
                color: #fff;
            }
            p { 
                font-size: 1.2em; 
                margin-bottom: 30px;
                line-height: 1.6;
            }
            .btn { 
                display: inline-block;
                padding: 12px 30px;
                background: white;
                color: #667eea;
                text-decoration: none;
                border-radius: 50px;
                font-weight: bold;
                transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            }
            .btn:hover { 
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(0,0,0,0.3);
            }
            .home-icon {
                font-size: 2em;
                margin-right: 10px;
                vertical-align: middle;
            }
        </style>
    </head>
    <body>
        <div class="error-container">
            <h1>🔍 404</h1>
            <p>La página que buscas no existe o ha sido movida.</p>
            <a href="/" class="btn">
                <span class="home-icon">🏠</span>
                Volver al inicio
            </a>
        </div>
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
            body { 
                font-family: 'Arial', sans-serif; 
                text-align: center; 
                padding: 50px; 
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                color: white;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
            }
            .error-container { 
                background: rgba(255, 255, 255, 0.1); 
                padding: 40px; 
                border-radius: 15px;
                backdrop-filter: blur(10px);
                max-width: 600px;
            }
            h1 { 
                font-size: 3em; 
                margin-bottom: 20px;
                color: #fff;
            }
            p { 
                font-size: 1.2em; 
                margin-bottom: 30px;
                line-height: 1.6;
            }
            .btn { 
                display: inline-block;
                padding: 12px 30px;
                background: white;
                color: #f5576c;
                text-decoration: none;
                border-radius: 50px;
                font-weight: bold;
                transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            }
            .btn:hover { 
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(0,0,0,0.3);
            }
            .refresh-icon {
                font-size: 2em;
                margin-right: 10px;
                vertical-align: middle;
            }
        </style>
    </head>
    <body>
        <div class="error-container">
            <h1>⚠️ 500</h1>
            <p>Algo salió mal en el servidor. Nuestro equipo ha sido notificado.</p>
            <a href="/" class="btn">
                <span class="refresh-icon">🔄</span>
                Volver a intentar
            </a>
        </div>
    </body>
    </html>
    ''', 500

# ==============================
# MIDDLEWARE PARA VERIFICAR CAJA
# ==============================
@app.before_request
def verificar_caja_para_usuarios_relevantes():
    """Verificar caja automáticamente para cajeros y admins"""
    # Solo aplicar a rutas que no sean login, logout, api o static
    if request.path.startswith('/login') or \
       request.path.startswith('/logout') or \
       request.path.startswith('/api/') or \
       request.path.startswith('/static/') or \
       request.path == '/':
        return
    
    # Solo para usuarios autenticados
    if 'user_id' in session:
        usuario_actual = get_usuario_actual()
        if usuario_actual and usuario_actual['rol'] in ['cajero', 'admin']:
            # Solo verificar en rutas importantes
            rutas_importantes = ['/caja', '/ventas', '/historial_caja']
            if request.path in rutas_importantes:
                try:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute("SELECT id FROM caja_turnos WHERE estado = 'abierta'")
                    if not cur.fetchone():
                        # Si llegamos aquí desde una ruta importante y no hay caja, redirigir
                        flash('Se requiere caja abierta para esta sección. Abriendo automáticamente...', 'info')
                        if abrir_caja_automaticamente():
                            return redirect(request.path)
                    cur.close()
                    conn.close()
                except Exception as e:
                    print(f"Error verificando caja en middleware: {e}")

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
