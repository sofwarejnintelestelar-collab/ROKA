# ==============================
# IMPORTS CORRECTOS
# ==============================
import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
import psycopg2
from datetime import datetime, date, timedelta
import json
import hashlib
from functools import wraps
from flask_socketio import SocketIO, emit, join_room, leave_room
import socket
import locale

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
# CONEXIÓN A BASE DE DATOS (CORREGIDO PARA RENDER)
# ==============================
def get_db_connection():
    try:
        # Intentar conectar a Render primero
        database_url = os.environ.get('DATABASE_URL')
        
        if database_url:
            # Asegurar formato correcto
            if database_url.startswith('postgres://'):
                database_url = database_url.replace('postgres://', 'postgresql://', 1)
            
            print(f"🔗 Conectando a Render DB...")
            return psycopg2.connect(database_url, sslmode='require')
        else:
            # Si no hay DATABASE_URL, usar conexión directa con tu URL
            print(f"🔗 Conectando a DB directa...")
            return psycopg2.connect(
                "postgresql://roka_user:0AjcpK5hyatis0VD91PRjUFlA1q0CsZn@dpg-d5ndakhr0fns73fgvmkg-a.virginia-postgres.render.com:5432/roka",
                sslmode='require'
            )
            
    except Exception as e:
        print(f"❌ Error conectando a DB: {e}")
        print("🔄 Intentando conexión local...")
        try:
            return psycopg2.connect(
                host="localhost",
                port="5432",
                database="roka",
                user="postgres",
                password="postgres"
            )
        except Exception as local_e:
            print(f"❌ Error conectando a DB local: {local_e}")
            # Crear una conexión de prueba para evitar errores
            raise ConnectionError("No se pudo conectar a ninguna base de datos")

# ==============================
# CREACIÓN DE TABLAS (SI NO EXISTEN)
# ==============================
def create_tables():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        print("🔄 Creando tablas...")
        
        # Tablas básicas
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
            CREATE TABLE IF NOT EXISTS categorias (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL UNIQUE,
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
                tipo VARCHAR(20) DEFAULT 'producto',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                fecha_cierre TIMESTAMP
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
                tiempo_fin TIMESTAMP
            )
        ''')
        
        # Datos iniciales
        cur.execute("SELECT COUNT(*) FROM categorias")
        if cur.fetchone()[0] == 0:
            categorias_default = ['ENTRADAS', 'PICADAS', 'EMPANADAS', 'MINUTAS', 'GUARNICIONES', 
                                 'PASTAS', 'SALSAS', 'PIZZAS', 'PLATOS ESPECIALES', 'POSTRES', 'HELADOS']
            for nombre in categorias_default:
                cur.execute("INSERT INTO categorias (nombre) VALUES (%s)", (nombre,))
        
        cur.execute("SELECT COUNT(*) FROM mesas")
        if cur.fetchone()[0] == 0:
            for i in range(1, 11):
                cur.execute("INSERT INTO mesas (numero, capacidad) VALUES (%s, %s)", (i, 4))
        
        cur.execute("SELECT COUNT(*) FROM usuarios WHERE username = 'admin'")
        if cur.fetchone()[0] == 0:
            password_hash = hashlib.sha256('admin123'.encode()).hexdigest()
            cur.execute('INSERT INTO usuarios (username, password_hash, nombre, email, rol) VALUES (%s, %s, %s, %s, %s)', 
                       ('admin', password_hash, 'Administrador', 'admin@sistema.com', 'admin'))
            cur.execute('INSERT INTO usuarios (username, password_hash, nombre, email, rol) VALUES (%s, %s, %s, %s, %s)', 
                       ('mozo', hashlib.sha256('mozo123'.encode()).hexdigest(), 'Mozo Principal', 'mozo@sistema.com', 'mozo'))
            cur.execute('INSERT INTO usuarios (username, password_hash, nombre, email, rol) VALUES (%s, %s, %s, %s, %s)', 
                       ('chef', hashlib.sha256('chef123'.encode()).hexdigest(), 'Chef Principal', 'chef@sistema.com', 'chef'))
            cur.execute('INSERT INTO usuarios (username, password_hash, nombre, email, rol) VALUES (%s, %s, %s, %s, %s)', 
                       ('cajero', hashlib.sha256('cajero123'.encode()).hexdigest(), 'Cajero Principal', 'cajero@sistema.com', 'cajero'))
        
        conn.commit()
        print("✅ Tablas creadas exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error creando tablas: {e}")
        return False
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

# ==============================
# RUTA DE INICIO - LOGIN
# ==============================
@app.route("/")
def index():
    """Página principal - Redirige a login"""
    return redirect(url_for('login'))

# ==============================
# LOGIN (SIMPLE)
# ==============================
@app.route("/login", methods=["GET", "POST"])
def login():
    """Página de login principal"""
    # Si ya está logueado, redirigir según rol
    if 'user_id' in session:
        usuario_actual = get_usuario_actual()
        if usuario_actual:
            return redirect_based_on_role(usuario_actual['rol'])
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        # Login simple con usuarios predefinidos
        usuarios = {
            'admin': {'password': 'admin123', 'nombre': 'Administrador', 'rol': 'admin'},
            'mozo': {'password': 'mozo123', 'nombre': 'Mozo Principal', 'rol': 'mozo'},
            'chef': {'password': 'chef123', 'nombre': 'Chef Principal', 'rol': 'chef'},
            'cajero': {'password': 'cajero123', 'nombre': 'Cajero Principal', 'rol': 'cajero'}
        }
        
        if username in usuarios and usuarios[username]['password'] == password:
            # Crear sesión
            session['user_id'] = 1  # ID fijo para simplificar
            session['username'] = username
            session['nombre'] = usuarios[username]['nombre']
            session['rol'] = usuarios[username]['rol']
            
            flash(f'Bienvenido {usuarios[username]["nombre"]}!', 'success')
            return redirect_based_on_role(usuarios[username]['rol'])
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    
    return render_template("login.html", ahora=datetime.now())

def redirect_based_on_role(rol):
    """Redirige según el rol del usuario"""
    if rol == 'chef':
        return redirect(url_for('chef'))
    elif rol == 'mozo':
        return redirect(url_for('mesas'))  # Cambié a mesas en lugar de ordenes
    elif rol == 'admin':
        return redirect(url_for('productos'))
    else:  # cajero u otros
        return redirect(url_for('caja'))

def get_usuario_actual():
    """Obtiene el usuario actual de la sesión"""
    if 'user_id' in session:
        return {
            'id': session['user_id'],
            'username': session.get('username'),
            'nombre': session.get('nombre'),
            'rol': session.get('rol')
        }
    return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Debes iniciar sesión primero', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==============================
# PANEL DEL CHEF
# ==============================
@app.route("/chef")
@login_required
def chef():
    """Panel del chef"""
    usuario_actual = get_usuario_actual()
    return render_template("chef.html", usuario=usuario_actual, ahora=datetime.now())

# ==============================
# CAJA
# ==============================
@app.route("/caja")
@login_required
def caja():
    """Panel de caja"""
    usuario_actual = get_usuario_actual()
    return render_template("caja.html", usuario=usuario_actual, ahora=datetime.now())

# ==============================
# MESAS
# ==============================
@app.route("/mesas")
@login_required
def mesas():
    """Lista de mesas"""
    usuario_actual = get_usuario_actual()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
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
                             ahora=datetime.now())
    except Exception as e:
        flash(f'Error cargando mesas: {str(e)}', 'danger')
        return render_template("mesas.html",
                             usuario=usuario_actual,
                             mesas=[],
                             ahora=datetime.now())

# ==============================
# PRODUCTOS
# ==============================
@app.route("/productos")
@login_required
def productos():
    """Lista de productos"""
    usuario_actual = get_usuario_actual()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT p.*, c.nombre as categoria_nombre 
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
                'codigo_barra': p[1], 
                'nombre': p[2],
                'precio': float(p[3]) if p[3] else 0,
                'stock': p[4] if p[4] else 0,
                'categoria_id': p[5], 
                'categoria_nombre': p[8] if p[8] else '',
                'tipo': p[6] if len(p) > 6 else 'producto'
            })
        
        cur.close()
        conn.close()
        
        return render_template("productos.html",
                             usuario=usuario_actual,
                             productos=productos_list,
                             categorias=[{'id': c[0], 'nombre': c[1]} for c in categorias_db],
                             ahora=datetime.now())
    except Exception as e:
        flash(f'Error cargando productos: {str(e)}', 'danger')
        return render_template("productos.html",
                             usuario=usuario_actual,
                             productos=[],
                             categorias=[],
                             ahora=datetime.now())

# ==============================
# API PARA EL CHEF
# ==============================
@app.route("/api/pedidos_cocina_comidas")
def api_pedidos_cocina_comidas():
    """API para pedidos de cocina"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT o.id as orden_id, m.numero as mesa_numero, o.mozo_nombre, 
                   o.estado as estado_orden, o.fecha_apertura, o.total
            FROM ordenes o 
            JOIN mesas m ON o.mesa_id = m.id 
            WHERE o.estado IN ('abierta', 'proceso')
            ORDER BY o.fecha_apertura ASC
        ''')
        
        pedidos_db = cur.fetchall()
        pedidos_list = []
        
        for pedido in pedidos_db:
            # Obtener items de esta orden
            cur.execute('''
                SELECT id, producto_nombre, cantidad, estado_item, observaciones
                FROM orden_items 
                WHERE orden_id = %s
            ''', (pedido[0],))
            
            items_db = cur.fetchall()
            items = []
            for item in items_db:
                items.append({
                    'id': item[0],
                    'producto_nombre': item[1],
                    'cantidad': item[2],
                    'estado_item': item[3] if item[3] else 'pendiente',
                    'observaciones': item[4]
                })
            
            items_pendientes = sum(1 for item in items if item['estado_item'] == 'pendiente')
            items_proceso = sum(1 for item in items if item['estado_item'] == 'proceso')
            items_listos = sum(1 for item in items if item['estado_item'] == 'listo')
            
            pedidos_list.append({
                'id': pedido[0], 
                'mesa_numero': pedido[1], 
                'mozo_nombre': pedido[2],
                'estado_orden': pedido[3], 
                'fecha_apertura': pedido[4].strftime('%H:%M') if pedido[4] else '',
                'total': float(pedido[5]) if pedido[5] else 0,
                'items': items,
                'estadisticas': {
                    'pendientes': items_pendientes, 
                    'proceso': items_proceso, 
                    'listos': items_listos, 
                    'total': len(items)
                }
            })
        
        cur.close()
        conn.close()
        
        return jsonify(pedidos_list)
    except Exception as e:
        print(f"Error en api_pedidos_cocina_comidas: {e}")
        return jsonify([])

@app.route("/api/actualizar_item_estado", methods=["POST"])
def api_actualizar_item_estado():
    """Actualizar estado de un item"""
    try:
        data = request.get_json()
        item_id = data.get('item_id')
        nuevo_estado = data.get('estado')
        
        if not item_id or not nuevo_estado:
            return jsonify({"success": False, "message": "Faltan datos"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        tiempo_actual = datetime.now()
        if nuevo_estado == 'proceso':
            cur.execute('UPDATE orden_items SET estado_item = %s, tiempo_inicio = %s WHERE id = %s', 
                       (nuevo_estado, tiempo_actual, item_id))
        elif nuevo_estado == 'listo':
            cur.execute('UPDATE orden_items SET estado_item = %s, tiempo_fin = %s WHERE id = %s', 
                       (nuevo_estado, tiempo_actual, item_id))
        else:
            cur.execute('UPDATE orden_items SET estado_item = %s WHERE id = %s', 
                       (nuevo_estado, item_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"success": True, "message": f"Estado actualizado a {nuevo_estado}"})
        
    except Exception as e:
        print(f"Error actualizando estado item: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

# ==============================
# API PARA MESAS Y PRODUCTOS
# ==============================
@app.route("/api/mesas")
def api_mesas():
    """API para obtener mesas"""
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
        
        cur.close()
        conn.close()
        return jsonify(mesas_list)
    except Exception as e:
        print(f"Error obteniendo mesas: {e}")
        return jsonify([])

@app.route("/api/productos")
def api_productos():
    """API para obtener productos"""
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
                'precio': float(p[2]) if p[2] else 0,
                'stock': p[3] if p[3] else 0,
                'tipo': p[4] if len(p) > 4 else 'producto'
            })
        
        cur.close()
        conn.close()
        return jsonify(productos_list)
    except Exception as e:
        print(f"Error obteniendo productos: {e}")
        return jsonify([])

# ==============================
# API PARA CREAR ORDEN
# ==============================
@app.route("/api/crear_orden", methods=["POST"])
@login_required
def api_crear_orden():
    """Crear una nueva orden"""
    try:
        data = request.get_json()
        mesa_id = data.get('mesa_id')
        mozo_nombre = data.get('mozo_nombre', 'Mozo')
        items = data.get('items', [])
        observaciones = data.get('observaciones', '')
        
        if not mesa_id or not items:
            return jsonify({"success": False, "message": "Datos incompletos"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Calcular total
        total = sum(item['precio_unitario'] * item['cantidad'] for item in items)
        
        # Crear orden
        cur.execute('''
            INSERT INTO ordenes (mesa_id, mozo_nombre, observaciones, total)
            VALUES (%s, %s, %s, %s) RETURNING id
        ''', (mesa_id, mozo_nombre, observaciones, total))
        
        orden_id = cur.fetchone()[0]
        
        # Crear items
        for item in items:
            cur.execute('''
                INSERT INTO orden_items (orden_id, producto_id, producto_nombre, cantidad, precio_unitario, observaciones)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (orden_id, item['producto_id'], item['producto_nombre'], 
                  item['cantidad'], item['precio_unitario'], 
                  item.get('observaciones', '')))
            
            # Actualizar stock si no es comida
            if item.get('tipo') != 'comida':
                cur.execute('UPDATE productos SET stock = stock - %s WHERE id = %s', 
                           (item['cantidad'], item['producto_id']))
        
        # Actualizar estado de la mesa
        cur.execute('UPDATE mesas SET estado = %s WHERE id = %s', ('ocupada', mesa_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"success": True, "orden_id": orden_id, "message": "Orden creada exitosamente"})
        
    except Exception as e:
        print(f"Error creando orden: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

# ==============================
# WEBSOCKETS (SIMPLIFICADOS)
# ==============================
@socketio.on('connect')
def handle_connect():
    print(f'✅ Cliente conectado: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    print(f'❌ Cliente desconectado: {request.sid}')

@socketio.on('join_chef')
def handle_join_chef(data):
    print(f'👨‍🍳 Chef conectado')
    emit('join_response', {'status': 'joined', 'rol': 'chef'})

# ==============================
# RUTAS ADICIONALES
# ==============================
@app.route("/ordenes")
@login_required
def ordenes():
    """Página de órdenes"""
    usuario_actual = get_usuario_actual()
    return render_template("ordenes.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/logout")
def logout():
    """Cerrar sesión"""
    session.clear()
    flash('Sesión cerrada correctamente', 'info')
    return redirect(url_for('login'))

# ==============================
# MANEJO DE ERRORES (SIN TEMPLATES)
# ==============================
@app.errorhandler(404)
def pagina_no_encontrada(e):
    return "<h1>404 - Página no encontrada</h1><p>La página que buscas no existe.</p><a href='/login'>Volver al login</a>", 404

@app.errorhandler(500)
def error_servidor(e):
    return "<h1>500 - Error del servidor</h1><p>Algo salió mal en el servidor.</p><a href='/login'>Volver al login</a>", 500

# ==============================
# INICIO DEL SERVIDOR
# ==============================
if __name__ == "__main__":
    # Intentar crear tablas al iniciar
    try:
        create_tables()
    except Exception as e:
        print(f"⚠️  No se pudieron crear tablas: {e}")
        print("⚠️  Continuando sin crear tablas...")
    
    # Configuración para Render
    port = int(os.environ.get("PORT", 5000))
    
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        allow_unsafe_werkzeug=False,
        use_reloader=False
    )
