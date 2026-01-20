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
# CONEXIÓN A BASE DE DATOS
# ==============================
def get_db_connection():
    # Para Render - URL completa proporcionada
    database_url = "postgresql://roka_db_user:tu_contraseña@dpg-d5ndakhr0fns73fgvmkg-a.oregon-postgres.render.com:5432/roka_db"
    
    try:
        # Para Render - conectar con SSL
        return psycopg2.connect(database_url, sslmode='require')
    except Exception as e:
        print(f"❌ Error conectando a DB: {e}")
        # Fallback local
        try:
            return psycopg2.connect(
                host="localhost",
                port="5432",
                database="roka",
                user="postgres",
                password="pm"
            )
        except:
            raise e

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

@socketio.on('join_mozo')
def handle_join_mozo(data):
    usuario_id = data.get('usuario_id')
    nombre = data.get('nombre')
    print(f'👤 Mozo {nombre} se unió')
    emit('join_response', {'status': 'joined', 'rol': 'mozo'})

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
# CREACIÓN DE TABLAS (SI NO EXISTEN) Y REPARACIÓN
# ==============================
def create_tables():
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Tablas existentes
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
        
        # TABLA PRODUCTOS CON CAMPO TIPO
        cur.execute('''
            CREATE TABLE IF NOT EXISTS productos (
                id SERIAL PRIMARY KEY,
                codigo_barra VARCHAR(50) UNIQUE,
                nombre VARCHAR(200) NOT NULL,
                precio DECIMAL(10,2) NOT NULL,
                stock INTEGER DEFAULT 0,
                categoria_id INTEGER,
                proveedor_id INTEGER,
                tipo VARCHAR(20) DEFAULT 'producto',  -- 'comida', 'bebida', 'producto'
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
        
        # Tabla para ventas/cierres
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
        
    except Exception as e:
        print(f"❌ Error creando tablas: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

# ==============================
# FUNCIÓN PARA REPARAR PRODUCTOS MAL CARGADOS
# ==============================
def reparar_productos():
    """Función para reparar productos con datos intercambiados"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # 1. Agregar columna tipo si no existe
        try:
            cur.execute("ALTER TABLE productos ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) DEFAULT 'producto'")
            conn.commit()
        except Exception as e:
            print(f"⚠️  La columna 'tipo' ya existe o no se pudo agregar: {e}")
        
        # 2. Buscar productos donde el nombre es un número (precio mal puesto)
        cur.execute("SELECT id, nombre, codigo_barra, precio FROM productos WHERE nombre ~ '^[0-9]+\.?[0-9]*$'")
        productos_malos = cur.fetchall()
        
        print(f"🔍 Encontré {len(productos_malos)} productos con datos intercambiados")
        
        for prod in productos_malos:
            prod_id, nombre_mal, codigo_barra_mal, precio_actual = prod
            
            # Si el "nombre" es realmente un precio, intercambiar
            try:
                # Intenta convertir el "nombre" a float
                precio_nuevo = float(nombre_mal)
                
                # Si el código de barras parece un nombre de producto
                if codigo_barra_mal and any(palabra in codigo_barra_mal.lower() for palabra in ['bife', 'chorizo', 'milanesa', 'pizza', 'empanada', 'rabas', 'langostinos']):
                    nombre_nuevo = codigo_barra_mal
                    
                    print(f"🔄 Corrigiendo producto ID {prod_id}:")
                    print(f"   Antes - Nombre: {nombre_mal}, Código: {codigo_barra_mal}, Precio: {precio_actual}")
                    print(f"   Después - Nombre: {nombre_nuevo}, Código: NULL, Precio: {precio_nuevo}, Tipo: comida")
                    
                    cur.execute("""
                        UPDATE productos 
                        SET nombre = %s, 
                            codigo_barra = NULL,
                            precio = %s,
                            tipo = 'comida',
                            stock = NULL
                        WHERE id = %s
                    """, (nombre_nuevo, precio_nuevo, prod_id))
            
            except ValueError:
                continue
        
        # 3. Verificar que todas las comidas tengan tipo='comida'
        cur.execute("""
            UPDATE productos 
            SET tipo = 'comida' 
            WHERE (nombre ILIKE '%bife%' OR nombre ILIKE '%milanesa%' OR nombre ILIKE '%pizza%' 
                   OR nombre ILIKE '%empanada%' OR nombre ILIKE '%rabas%' OR nombre ILIKE '%langostinos%')
            AND tipo != 'comida'
        """)
        
        # 4. Para comidas, establecer stock=NULL
        cur.execute("UPDATE productos SET stock = NULL WHERE tipo = 'comida'")
        
        conn.commit()
        print("✅ Productos reparados exitosamente")
        
    except Exception as e:
        print(f"❌ Error reparando productos: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

# ==============================
# FUNCIONES DE AUTENTICACIÓN
# ==============================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, password_hash):
    return hash_password(password) == password_hash

def login_user(username, password):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT id, username, password_hash, nombre, rol FROM usuarios WHERE username = %s AND activo = true', (username,))
        usuario = cur.fetchone()
        if usuario and verify_password(password, usuario[2]):
            return {'id': usuario[0], 'username': usuario[1], 'nombre': usuario[3], 'rol': usuario[4]}
        return None
    except Exception as e:
        print(f"❌ Error en login: {e}")
        return None
    finally:
        cur.close()
        conn.close()

def get_usuario_actual():
    if 'user_id' in session:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute('SELECT id, username, nombre, rol FROM usuarios WHERE id = %s', (session['user_id'],))
            usuario = cur.fetchone()
            if usuario:
                return {'id': usuario[0], 'username': usuario[1], 'nombre': usuario[2], 'rol': usuario[3]}
        except Exception as e:
            print(f"❌ Error obteniendo usuario: {e}")
        finally:
            cur.close()
            conn.close()
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
    """Página principal - Redirige a chef directamente"""
    return redirect(url_for('chef'))

@app.route("/login", methods=["GET", "POST"])
def login():
    """Login para sistema POS (opcional)"""
    if 'user_id' in session:
        usuario_actual = get_usuario_actual()
        if usuario_actual:
            flash(f'Ya estás logueado como {usuario_actual["nombre"]}', 'info')
            
            # Redirigir según rol
            if usuario_actual['rol'] == 'chef':
                return redirect(url_for('chef'))
            elif usuario_actual['rol'] == 'mozo':
                return redirect(url_for('ordenes'))
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
            
            # Redirigir según rol
            if usuario['rol'] == 'chef':
                print(f"👨‍🍳 Chef {usuario['nombre']} inició sesión")
                return redirect(url_for('chef'))
            elif usuario['rol'] == 'mozo':
                return redirect(url_for('ordenes'))
            else:
                return redirect(url_for('caja'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    
    # Mostrar formulario de login
    ahora_formateado = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    return render_template("login.html", 
                         ahora=ahora_formateado,
                         usuarios_default=[
                             {'username': 'admin', 'password': 'admin123', 'rol': 'Admin'},
                             {'username': 'chef', 'password': 'chef123', 'rol': 'Chef'},
                             {'username': 'mozo', 'password': 'mozo123', 'rol': 'Mozo'},
                             {'username': 'cajero', 'password': 'cajero123', 'rol': 'Cajero'}
                         ])

@app.route("/caja")
@login_required
def caja():
    """Panel de caja - requiere login"""
    orden_id = request.args.get('orden_id', type=int)
    usuario_actual = get_usuario_actual()
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM caja_turnos WHERE estado = 'abierta' ORDER BY fecha_apertura DESC LIMIT 1")
    turno_db = cur.fetchone()
    
    turno_abierto = None
    if turno_db:
        turno_abierto = {
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
    
    cur.execute('SELECT o.id, m.numero as mesa_numero, o.mozo_nombre, o.total FROM ordenes o JOIN mesas m ON o.mesa_id = m.id WHERE o.estado = %s ORDER BY o.fecha_apertura DESC', ('abierta',))
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
    
    if not turno_abierto:
        return render_template("caja_sin_turno.html", 
                             usuario=usuario_actual, 
                             ahora=datetime.now(),
                             ordenes_abiertas=ordenes_abiertas)
    
    return render_template("caja.html", 
                         turno_abierto=turno_abierto, 
                         usuario=usuario_actual, 
                         ahora=datetime.now(), 
                         ordenes_abiertas=ordenes_abiertas)

# ==============================
# PANEL DEL CHEF - ACCESO LIBRE
# ==============================
@app.route("/chef")
def chef():
    """Panel del chef - ACCESO LIBRE PARA TODOS"""
    # Crear usuario temporal para el chef
    usuario_temporal = {
        'id': 999,
        'username': 'chef_publico',
        'nombre': 'Cocina Pública',
        'rol': 'chef'
    }
    
    print(f"👨‍🍳 Acceso público al panel del chef desde IP: {request.remote_addr}")
    
    return render_template("chef.html", 
                         usuario=usuario_temporal,
                         ahora=datetime.now())

# ==============================
# API ENDPOINTS PÚBLICOS PARA CHEF
# ==============================
@app.route("/api/pedidos_cocina_comidas")
def api_pedidos_cocina_comidas():
    """API pública para mostrar solo comidas en la cocina"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id FROM categorias 
            WHERE UPPER(nombre) NOT LIKE '%BEBIDA%' 
            AND UPPER(nombre) NOT LIKE '%PARA TOMAR%'
            AND UPPER(nombre) NOT LIKE '%BEBESTIBLE%'
        """)
        categorias_comida = [row[0] for row in cur.fetchall()]
        
        if not categorias_comida:
            cur.execute("SELECT id, nombre FROM categorias")
            todas_categorias = cur.fetchall()
            for cat_id, cat_nombre in todas_categorias:
                if 'BEBIDA' not in cat_nombre.upper() and 'PARA TOMAR' not in cat_nombre.upper():
                    categorias_comida.append(cat_id)
        
        if not categorias_comida:
            return jsonify([])
        
        cur.execute('''
            SELECT o.id as orden_id, m.numero as mesa_numero, o.mozo_nombre, 
                   o.estado as estado_orden, o.fecha_apertura, o.total, 
                   json_agg(json_build_object(
                       'id', oi.id, 
                       'producto_nombre', oi.producto_nombre, 
                       'cantidad', oi.cantidad, 
                       'precio_unitario', oi.precio_unitario, 
                       'estado_item', COALESCE(oi.estado_item, 'pendiente'), 
                       'observaciones', oi.observaciones, 
                       'tiempo_inicio', oi.tiempo_inicio, 
                       'tiempo_fin', oi.tiempo_fin,
                       'producto_id', oi.producto_id
                   )) as items
            FROM ordenes o 
            JOIN mesas m ON o.mesa_id = m.id 
            JOIN orden_items oi ON o.id = oi.orden_id
            JOIN productos p ON oi.producto_id = p.id
            WHERE o.estado IN ('abierta', 'proceso') 
            AND p.tipo = 'comida'
            GROUP BY o.id, m.numero, o.mozo_nombre, o.estado, o.fecha_apertura, o.total 
            ORDER BY o.fecha_apertura ASC
        ''')
        
        pedidos_db = cur.fetchall()
        pedidos_list = []
        
        for pedido in pedidos_db:
            items = pedido[6] if pedido[6] else []
            if items:
                items_pendientes = sum(1 for item in items if item['estado_item'] == 'pendiente')
                items_proceso = sum(1 for item in items if item['estado_item'] == 'proceso')
                items_listos = sum(1 for item in items if item['estado_item'] == 'listo')
                
                # CORRECCIÓN: Asegurar que total sea float
                total_valor = float(pedido[5]) if pedido[5] is not None else 0.0
                
                pedidos_list.append({
                    'id': pedido[0], 
                    'mesa_numero': pedido[1], 
                    'mozo_nombre': pedido[2],
                    'estado_orden': pedido[3], 
                    'fecha_apertura': pedido[4].strftime('%H:%M') if pedido[4] else '',
                    'total': total_valor,  # Ya convertido a float
                    'items': items,
                    'estadisticas': {
                        'pendientes': items_pendientes, 
                        'proceso': items_proceso, 
                        'listos': items_listos, 
                        'total': len(items)
                    }
                })
        
        return jsonify(pedidos_list)
    except Exception as e:
        print(f"Error obteniendo pedidos cocina comidas: {e}")
        return jsonify([])
    finally:
        cur.close()
        conn.close()

@app.route("/api/actualizar_item_estado", methods=["POST"])
def api_actualizar_item_estado():
    """API pública para actualizar estado de items"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data"}), 400
        
        item_id = data.get('item_id')
        nuevo_estado = data.get('estado')
        
        if not item_id or not nuevo_estado:
            return jsonify({"success": False, "message": "Faltan datos"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('SELECT oi.id, oi.producto_nombre, oi.orden_id, m.numero as mesa_numero FROM orden_items oi JOIN ordenes o ON oi.orden_id = o.id JOIN mesas m ON o.mesa_id = m.id WHERE oi.id = %s', (item_id,))
            item_info = cur.fetchone()
            if not item_info:
                return jsonify({"success": False, "message": "Item no encontrado"}), 404
            
            producto_nombre = item_info[1]
            orden_id = item_info[2]
            mesa_numero = item_info[3]
            
            tiempo_actual = datetime.now()
            if nuevo_estado == 'proceso':
                cur.execute('UPDATE orden_items SET estado_item = %s, tiempo_inicio = %s WHERE id = %s', (nuevo_estado, tiempo_actual, item_id))
            elif nuevo_estado == 'listo':
                cur.execute('UPDATE orden_items SET estado_item = %s, tiempo_fin = %s WHERE id = %s', (nuevo_estado, tiempo_actual, item_id))
            else:
                cur.execute('UPDATE orden_items SET estado_item = %s WHERE id = %s', (nuevo_estado, item_id))
            
            cur.execute('SELECT o.id, COUNT(oi.id) as total_items, SUM(CASE WHEN oi.estado_item = %s THEN 1 ELSE 0 END) as items_listos FROM ordenes o JOIN orden_items oi ON o.id = oi.orden_id WHERE oi.id = %s GROUP BY o.id', ('listo', item_id))
            resultado = cur.fetchone()
            if resultado:
                orden_id = resultado[0]
                total_items = resultado[1]
                items_listos = resultado[2]
                if total_items == items_listos:
                    cur.execute('UPDATE ordenes SET estado = %s WHERE id = %s', ('listo', orden_id))
            
            conn.commit()
            
            # Notificar a todos sobre el cambio de estado
            now = datetime.now()
            socketio.emit('cambiar_estado_item_chef', {
                'item_id': item_id, 
                'orden_id': orden_id, 
                'nuevo_estado': nuevo_estado,
                'producto_nombre': producto_nombre, 
                'mesa_numero': mesa_numero,
                'timestamp': now.strftime('%H:%M:%S')
            }, namespace='/chef')
            
            socketio.emit('cambiar_estado_item_ws', {
                'item_id': item_id, 
                'orden_id': orden_id, 
                'nuevo_estado': nuevo_estado,
                'producto_nombre': producto_nombre, 
                'mesa_numero': mesa_numero,
                'timestamp': now.strftime('%H:%M:%S')
            })
            
            return jsonify({"success": True, "message": f"Estado actualizado a {nuevo_estado}"})
            
        except Exception as e:
            conn.rollback()
            print(f"Error actualizando estado item: {e}")
            return jsonify({"success": False, "message": str(e)}), 500
        finally:
            cur.close()
            conn.close()
            
    except Exception as e:
        print(f"Error en api_actualizar_item_estado: {e}")
        return jsonify({"success": False, "message": "Error del servidor"}), 500

# ==============================
# RUTAS PARA PRODUCTOS
# ==============================
@app.route("/productos")
@login_required
def productos():
    """Lista de productos"""
    usuario_actual = get_usuario_actual()
    search = request.args.get('search', '')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if search:
        cur.execute('''
            SELECT 
                p.id,
                p.codigo_barra,
                p.nombre,
                p.precio,
                p.stock,
                p.categoria_id,
                p.proveedor_id,
                p.tipo,
                c.nombre as categoria_nombre,
                pr.nombre as proveedor_nombre
            FROM productos p 
            LEFT JOIN categorias c ON p.categoria_id = c.id 
            LEFT JOIN proveedores pr ON p.proveedor_id = pr.id
            WHERE p.nombre ILIKE %s OR p.codigo_barra ILIKE %s
            ORDER BY p.tipo, p.nombre
        ''', (f'%{search}%', f'%{search}%'))
    else:
        cur.execute('''
            SELECT 
                p.id,
                p.codigo_barra,
                p.nombre,
                p.precio,
                p.stock,
                p.categoria_id,
                p.proveedor_id,
                p.tipo,
                c.nombre as categoria_nombre,
                pr.nombre as proveedor_nombre
            FROM productos p 
            LEFT JOIN categorias c ON p.categoria_id = c.id 
            LEFT JOIN proveedores pr ON p.proveedor_id = pr.id
            ORDER BY p.tipo, p.nombre
        ''')
    
    productos_db = cur.fetchall()
    cur.execute('SELECT id, nombre FROM categorias ORDER BY nombre')
    categorias_db = cur.fetchall()
    cur.execute('SELECT id, nombre FROM proveedores WHERE activo = true ORDER BY nombre')
    proveedores_db = cur.fetchall()
    
    cur.close()
    conn.close()
    
    productos_list = []
    for p in productos_db:
        # CORRECCIÓN: Mapeo correcto de columnas
        # 0:id, 1:codigo_barra, 2:nombre, 3:precio, 4:stock, 
        # 5:categoria_id, 6:proveedor_id, 7:tipo, 8:categoria_nombre, 9:proveedor_nombre
        
        tipo = p[7] if len(p) > 7 else 'producto'
        
        # Para comidas: no hay stock (stock=NULL)
        if tipo == 'comida':
            stock_int = None
            mostrar_stock = False
            es_comida = True
        else:
            # Para productos/bebidas: sí hay stock
            stock_value = p[4]
            if stock_value is None:
                stock_int = 0
            else:
                try:
                    stock_int = int(stock_value)
                except (ValueError, TypeError):
                    stock_int = 0
            mostrar_stock = True
            es_comida = False
        
        # Convertir precio a float
        precio_value = p[3]
        if precio_value is None:
            precio_float = 0.0
        else:
            try:
                precio_float = float(precio_value)
            except (ValueError, TypeError):
                precio_float = 0.0
        
        # Obtener nombre de categoría
        categoria_nombre = str(p[8]) if p[8] is not None else ''
        
        productos_list.append({
            'id': p[0], 
            'codigo_barra': p[1] if tipo != 'comida' else '',  # Comidas sin código
            'nombre': p[2],  # ← COLUMNA CORRECTA
            'precio': precio_float,  # ← COLUMNA CORRECTA
            'stock': stock_int,
            'categoria_id': p[5], 
            'proveedor_id': p[6],
            'categoria_nombre': categoria_nombre,
            'proveedor_nombre': str(p[9]) if p[9] is not None else 'Sin proveedor',
            'tipo': tipo,
            'mostrar_stock': mostrar_stock,
            'es_comida': es_comida
        })
    
    return render_template("productos.html", 
                         usuario=usuario_actual,
                         productos=productos_list,
                         categorias=[{'id': c[0], 'nombre': c[1]} for c in categorias_db],
                         proveedores=[{'id': p[0], 'nombre': p[1]} for p in proveedores_db],
                         search=search,
                         ahora=datetime.now())

@app.route("/crear_producto", methods=["GET", "POST"])
@login_required
def crear_producto():
    """Crear nuevo producto"""
    usuario_actual = get_usuario_actual()
    
    if request.method == "POST":
        codigo_barra = request.form.get("codigo_barra", "").strip()
        nombre = request.form.get("nombre", "").strip()
        precio = request.form.get("precio", "0")
        stock = request.form.get("stock", "0")
        categoria_id = request.form.get("categoria_id")
        proveedor_id = request.form.get("proveedor_id")
        tipo = request.form.get("tipo", "producto")  # 'comida', 'bebida', 'producto'
        
        if not nombre or not precio:
            flash('Nombre y precio son requeridos', 'danger')
            return redirect(url_for('crear_producto'))
        
        try:
            precio_float = float(precio)
        except ValueError:
            flash('Precio debe ser un número válido', 'danger')
            return redirect(url_for('crear_producto'))
        
        # Para comidas: stock = NULL, código opcional
        if tipo == 'comida':
            stock_int = None
            # Para comidas: código de barras opcional, generar automático si está vacío
            if not codigo_barra:
                codigo_barra = f"COM{datetime.now().strftime('%Y%m%d%H%M%S')}"
        else:
            # Para productos y bebidas: stock requerido, código de barras requerido
            if not codigo_barra:
                flash('Código de barras requerido para productos y bebidas', 'danger')
                return redirect(url_for('crear_producto'))
            
            try:
                # Convertir stock a entero, manejando casos vacíos
                if stock and stock.strip():
                    stock_int = int(stock)
                else:
                    stock_int = 0
            except ValueError:
                flash('Stock debe ser un número válido', 'danger')
                return redirect(url_for('crear_producto'))
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('''
                INSERT INTO productos (codigo_barra, nombre, precio, stock, categoria_id, proveedor_id, tipo) 
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
            ''', (codigo_barra, nombre, precio_float, stock_int, 
                  categoria_id if categoria_id else None, 
                  proveedor_id if proveedor_id else None,
                  tipo))
            
            producto_id = cur.fetchone()[0]
            conn.commit()
            
            flash(f'Producto "{nombre}" creado exitosamente', 'success')
            return redirect(url_for('productos'))
            
        except Exception as e:
            conn.rollback()
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                flash(f'El código de barras "{codigo_barra}" ya existe', 'danger')
            else:
                flash(f'Error al crear producto: {str(e)}', 'danger')
            return redirect(url_for('crear_producto'))
        finally:
            cur.close()
            conn.close()
    
    # GET request - mostrar formulario
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT id, nombre FROM categorias ORDER BY nombre')
    categorias = cur.fetchall()
    
    cur.execute('SELECT id, nombre FROM proveedores WHERE activo = true ORDER BY nombre')
    proveedores = cur.fetchall()
    
    cur.close()
    conn.close()
    
    categorias_list = [{'id': c[0], 'nombre': c[1]} for c in categorias]
    proveedores_list = [{'id': p[0], 'nombre': p[1]} for p in proveedores]
    
    # Tipos disponibles
    tipos = [
        {'valor': 'comida', 'nombre': 'Comida (plato del menú)'},
        {'valor': 'bebida', 'nombre': 'Bebida (con stock)'},
        {'valor': 'producto', 'nombre': 'Producto/Insumo (con stock)'}
    ]
    
    return render_template("crear_producto.html",
                         usuario=usuario_actual,
                         categorias=categorias_list,
                         proveedores=proveedores_list,
                         tipos=tipos,
                         ahora=datetime.now())

@app.route("/editar_producto/<int:id>", methods=["GET", "POST"])
@login_required
def editar_producto(id):
    """Editar producto existente"""
    usuario_actual = get_usuario_actual()
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "GET":
        # CONSULTA MEJORADA: Seleccionar columnas por nombre y en orden correcto
        cur.execute('''
            SELECT 
                p.id,
                p.nombre,
                p.precio,
                p.tipo,
                p.categoria_id,
                p.codigo_barra,
                p.stock,
                p.proveedor_id,
                c.nombre as categoria_nombre
            FROM productos p 
            LEFT JOIN categorias c ON p.categoria_id = c.id
            WHERE p.id = %s
        ''', (id,))
        
        producto_db = cur.fetchone()
        
        if not producto_db:
            cur.close()
            conn.close()
            flash('Producto no encontrado', 'danger')
            return redirect(url_for('productos'))
        
        # CORRECCIÓN: Mapeo CORRECTO de columnas por posición
        # Columnas: 0:id, 1:nombre, 2:precio, 3:tipo, 4:categoria_id, 
        # 5:codigo_barra, 6:stock, 7:proveedor_id, 8:categoria_nombre
        
        tipo = producto_db[3] if len(producto_db) > 3 else 'producto'
        
        # Para comidas: stock es NULL
        stock_value = producto_db[6]
        if tipo == 'comida':
            stock_display = None
        else:
            try:
                stock_display = int(stock_value) if stock_value is not None else 0
            except (ValueError, TypeError):
                stock_display = 0
        
        producto = {
            'id': producto_db[0],           # id
            'nombre': producto_db[1],       # nombre ← CORRECTO
            'precio': float(producto_db[2]) if producto_db[2] else 0,  # precio ← CORRECTO
            'tipo': tipo,                   # tipo
            'categoria_id': producto_db[4], # categoria_id
            'codigo_barra': producto_db[5], # codigo_barra
            'stock': stock_display,         # stock
            'proveedor_id': producto_db[7] if len(producto_db) > 7 else None,  # proveedor_id
            'categoria_nombre': producto_db[8] if len(producto_db) > 8 else ''  # categoria_nombre
        }
        
        cur.execute('SELECT id, nombre FROM categorias ORDER BY nombre')
        categorias = cur.fetchall()
        
        cur.execute('SELECT id, nombre FROM proveedores WHERE activo = true ORDER BY nombre')
        proveedores = cur.fetchall()
        
        cur.close()
        conn.close()
        
        categorias_list = [{'id': c[0], 'nombre': c[1]} for c in categorias]
        proveedores_list = [{'id': p[0], 'nombre': p[1]} for p in proveedores]
        
        # Tipos disponibles
        tipos = [
            {'valor': 'comida', 'nombre': 'Comida (plato del menú)'},
            {'valor': 'bebida', 'nombre': 'Bebida (con stock)'},
            {'valor': 'producto', 'nombre': 'Producto/Insumo (con stock)'}
        ]
        
        return render_template("editar_producto.html",
                             usuario=usuario_actual,
                             producto=producto,
                             categorias=categorias_list,
                             proveedores=proveedores_list,
                             tipos=tipos,
                             ahora=datetime.now())
    
    if request.method == "POST":
        codigo_barra = request.form.get("codigo_barra", "").strip()
        nombre = request.form.get("nombre", "").strip()
        precio = request.form.get("precio", "0")
        stock = request.form.get("stock", "0")
        categoria_id = request.form.get("categoria_id")
        proveedor_id = request.form.get("proveedor_id")
        tipo = request.form.get("tipo", "producto")
        
        if not nombre or not precio:
            flash('Nombre y precio son requeridos', 'danger')
            return redirect(url_for('editar_producto', id=id))
        
        try:
            precio_float = float(precio)
        except ValueError:
            flash('Precio debe ser un número válido', 'danger')
            return redirect(url_for('editar_producto', id=id))
        
        # Para comidas: stock = NULL, código de barras opcional
        if tipo == 'comida':
            stock_int = None
            # Si el código de barras está vacío, dejarlo como NULL
            if not codigo_barra:
                codigo_barra = None
        else:
            # Para productos y bebidas: stock requerido, código de barras requerido
            if not codigo_barra:
                flash('Código de barras requerido para productos y bebidas', 'danger')
                return redirect(url_for('editar_producto', id=id))
            
            try:
                # Convertir stock a entero, manejando casos vacíos
                if stock and stock.strip():
                    stock_int = int(stock)
                else:
                    stock_int = 0
            except ValueError:
                flash('Stock debe ser un número válido', 'danger')
                return redirect(url_for('editar_producto', id=id))
        
        try:
            cur.execute('''
                UPDATE productos 
                SET codigo_barra = %s, nombre = %s, precio = %s, stock = %s, 
                    categoria_id = %s, proveedor_id = %s, tipo = %s
                WHERE id = %s
            ''', (codigo_barra, nombre, precio_float, stock_int,
                  categoria_id if categoria_id else None,
                  proveedor_id if proveedor_id else None,
                  tipo, id))
            
            conn.commit()
            flash(f'Producto "{nombre}" actualizado exitosamente', 'success')
            return redirect(url_for('productos'))
            
        except Exception as e:
            conn.rollback()
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                flash(f'El código de barras "{codigo_barra}" ya existe', 'danger')
            else:
                flash(f'Error al actualizar producto: {str(e)}', 'danger')
            return redirect(url_for('editar_producto', id=id))
        finally:
            cur.close()
            conn.close()

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

# ==============================
# RUTAS PARA MESAS (CORREGIDO)
# ==============================
@app.route("/mesas")
@login_required
def mesas():
    """Lista de mesas"""
    usuario_actual = get_usuario_actual()
    search = request.args.get('search', '')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if search:
        cur.execute('SELECT * FROM mesas WHERE CAST(numero AS TEXT) ILIKE %s OR ubicacion ILIKE %s ORDER BY numero', (f'%{search}%', f'%{search}%'))
    else:
        cur.execute('SELECT * FROM mesas ORDER BY numero')
    
    mesas_db = cur.fetchall()
    
    cur.close()
    conn.close()
    
    mesas_list = []
    for mesa in mesas_db:
        mesas_list.append({
            'id': mesa[0],
            'numero': mesa[1],
            'capacidad': mesa[2],
            'estado': mesa[3],
            'ubicacion': mesa[4],
            'created_at': mesa[5]
        })
    
    return render_template("mesas.html",
                         usuario=usuario_actual,
                         mesas=mesas_list,
                         search=search,
                         ahora=datetime.now())

@app.route("/crear_mesa", methods=["GET", "POST"])
@login_required
def crear_mesa():
    """Crear nueva mesa"""
    usuario_actual = get_usuario_actual()
    
    if request.method == "POST":
        numero = request.form.get("numero")
        capacidad = request.form.get("capacidad", 4)
        ubicacion = request.form.get("ubicacion", "")
        
        if not numero:
            flash('Número de mesa requerido', 'danger')
            return redirect(url_for('crear_mesa'))
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('INSERT INTO mesas (numero, capacidad, ubicacion) VALUES (%s, %s, %s)', 
                       (numero, capacidad, ubicacion))
            conn.commit()
            flash(f'Mesa #{numero} creada exitosamente', 'success')
            return redirect(url_for('mesas'))
            
        except Exception as e:
            conn.rollback()
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                flash(f'La mesa #{numero} ya existe', 'danger')
            else:
                flash(f'Error al crear mesa: {str(e)}', 'danger')
            return redirect(url_for('crear_mesa'))
        finally:
            cur.close()
            conn.close()
    
    return render_template("crear_mesa.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/editar_mesa/<int:id>", methods=["GET", "POST"])
@login_required
def editar_mesa(id):
    """Editar mesa existente"""
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
        
        usuario_actual = get_usuario_actual()
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
            conn.rollback()
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                flash(f'La mesa #{numero} ya existe', 'danger')
            else:
                flash(f'Error al actualizar mesa: {str(e)}', 'danger')
            return redirect(url_for('editar_mesa', id=id))
        finally:
            cur.close()
            conn.close()

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

# ==============================
# RUTAS PARA ORDENES
# ==============================
@app.route("/ordenes")
@login_required
def ordenes():
    usuario_actual = get_usuario_actual()
    return render_template("ordenes.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/ver_orden/<int:orden_id>")
@login_required
def ver_orden(orden_id):
    usuario_actual = get_usuario_actual()
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('''
            SELECT o.*, m.numero as mesa_numero 
            FROM ordenes o 
            JOIN mesas m ON o.mesa_id = m.id 
            WHERE o.id = %s
        ''', (orden_id,))
        orden_db = cur.fetchone()
        
        if not orden_db:
            flash('Orden no encontrada', 'danger')
            return redirect(url_for('ordenes'))
        
        orden = {
            'id': orden_db[0], 'mesa_id': orden_db[1], 'mesa_numero': orden_db[9],
            'mozo_nombre': orden_db[2], 'estado': orden_db[3], 'observaciones': orden_db[4],
            'total': float(orden_db[5]) if orden_db[5] else 0, 'fecha_apertura': orden_db[6]
        }
        
        cur.execute('SELECT * FROM orden_items WHERE orden_id = %s ORDER BY id', (orden_id,))
        items_db = cur.fetchall()
        
        items = []
        for item in items_db:
            items.append({
                'id': item[0], 'producto_nombre': item[3], 'cantidad': item[4],
                'precio_unitario': float(item[5]) if item[5] else 0,
                'observaciones': item[6], 'estado_item': item[7]
            })
        
        cur.close()
        conn.close()
        
        return render_template("ver_orden.html",
                             usuario=usuario_actual,
                             orden=orden,
                             items=items,
                             ahora=datetime.now())
        
    except Exception as e:
        print(f"Error obteniendo orden: {e}")
        flash('Error al obtener orden', 'danger')
        return redirect(url_for('ordenes'))

# ==============================
# RUTAS PARA CATEGORÍAS
# ==============================
@app.route("/categorias")
@login_required
def categorias():
    """Lista de categorías"""
    usuario_actual = get_usuario_actual()
    search = request.args.get('search', '')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if search:
        cur.execute('SELECT * FROM categorias WHERE nombre ILIKE %s ORDER BY nombre', (f'%{search}%',))
    else:
        cur.execute('SELECT * FROM categorias ORDER BY nombre')
    
    categorias_db = cur.fetchall()
    
    cur.close()
    conn.close()
    
    categorias_list = []
    for cat in categorias_db:
        categorias_list.append({
            'id': cat[0],
            'nombre': cat[1],
            'created_at': cat[2]
        })
    
    return render_template("categorias.html",
                         usuario=usuario_actual,
                         categorias=categorias_list,
                         search=search,
                         ahora=datetime.now())

@app.route("/crear_categoria", methods=["GET", "POST"])
@login_required
def crear_categoria():
    """Crear nueva categoría"""
    usuario_actual = get_usuario_actual()
    
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        
        if not nombre:
            flash('Nombre de categoría requerido', 'danger')
            return redirect(url_for('crear_categoria'))
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('INSERT INTO categorias (nombre) VALUES (%s)', (nombre,))
            conn.commit()
            flash(f'Categoría "{nombre}" creada exitosamente', 'success')
            return redirect(url_for('categorias'))
            
        except Exception as e:
            conn.rollback()
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                flash(f'La categoría "{nombre}" ya existe', 'danger')
            else:
                flash(f'Error al crear categoría: {str(e)}', 'danger')
            return redirect(url_for('crear_categoria'))
        finally:
            cur.close()
            conn.close()
    
    return render_template("crear_categoria.html",
                         usuario=usuario_actual,
                         ahora=datetime.now())

@app.route("/editar_categoria/<int:id>", methods=["GET", "POST"])
@login_required
def editar_categoria(id):
    """Editar categoría existente"""
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
        
        usuario_actual = get_usuario_actual()
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
            flash(f'Categoría actualizada a "{nombre}" exitosamente', 'success')
            return redirect(url_for('categorias'))
            
        except Exception as e:
            conn.rollback()
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                flash(f'La categoría "{nombre}" ya existe', 'danger')
            else:
                flash(f'Error al actualizar categoría: {str(e)}', 'danger')
            return redirect(url_for('editar_categoria', id=id))
        finally:
            cur.close()
            conn.close()

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

# ==============================
# RUTAS PARA PROVEEDORES
# ==============================
@app.route("/proveedores")
@login_required
def proveedores():
    """Lista de proveedores"""
    usuario_actual = get_usuario_actual()
    search = request.args.get('search', '')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if search:
        cur.execute('SELECT * FROM proveedores WHERE nombre ILIKE %s OR contacto ILIKE %s ORDER BY nombre', (f'%{search}%', f'%{search}%'))
    else:
        cur.execute('SELECT * FROM proveedores ORDER BY nombre')
    
    proveedores_db = cur.fetchall()
    
    cur.close()
    conn.close()
    
    proveedores_list = []
    for prov in proveedores_db:
        proveedores_list.append({
            'id': prov[0],
            'nombre': prov[1],
            'contacto': prov[2],
            'telefono': prov[3],
            'email': prov[4],
            'direccion': prov[5],
            'activo': prov[6],
            'created_at': prov[7]
        })
    
    return render_template("proveedores.html",
                         usuario=usuario_actual,
                         proveedores=proveedores_list,
                         search=search,
                         ahora=datetime.now())

@app.route("/crear_proveedor", methods=["GET", "POST"])
@login_required
def crear_proveedor():
    """Crear nuevo proveedor"""
    usuario_actual = get_usuario_actual()
    
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        contacto = request.form.get("contacto", "").strip()
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip()
        direccion = request.form.get("direccion", "").strip()
        
        if not nombre:
            flash('Nombre de proveedor requerido', 'danger')
            return redirect(url_for('crear_proveedor'))
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('INSERT INTO proveedores (nombre, contacto, telefono, email, direccion) VALUES (%s, %s, %s, %s, %s)', 
                       (nombre, contacto, telefono, email, direccion))
            conn.commit()
            flash(f'Proveedor "{nombre}" creado exitosamente', 'success')
            return redirect(url_for('proveedores'))
            
        except Exception as e:
            conn.rollback()
            flash(f'Error al crear proveedor: {str(e)}', 'danger')
            return redirect(url_for('crear_proveedor'))
        finally:
            cur.close()
            conn.close()
    
    return render_template("crear_proveedor.html",
                         usuario=usuario_actual,
                         ahora=datetime.now())

@app.route("/editar_proveedor/<int:id>", methods=["GET", "POST"])
@login_required
def editar_proveedor(id):
    """Editar proveedor existente"""
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
        
        usuario_actual = get_usuario_actual()
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
            conn.rollback()
            flash(f'Error al actualizar proveedor: {str(e)}', 'danger')
            return redirect(url_for('editar_proveedor', id=id))
        finally:
            cur.close()
            conn.close()

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
# RUTAS PARA VENTAS Y CIERRES DE CAJA (CORREGIDO)
# ==============================
@app.route("/ventas")
@login_required
def ventas():
    """Reporte de ventas"""
    usuario_actual = get_usuario_actual()
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Query para órdenes cerradas
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
    
    # Calcular totales
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
    
    # Obtener productos más vendidos
    cur.execute('''
        SELECT oi.producto_nombre, 
               SUM(oi.cantidad) as cantidad_total,
               SUM(oi.cantidad * oi.precio_unitario) as total_ventas
        FROM orden_items oi
        JOIN ordenes o ON oi.orden_id = o.id
        WHERE o.estado = 'cerrada'
        GROUP BY oi.producto_nombre
        ORDER BY cantidad_total DESC
        LIMIT 10
    ''')
    
    productos_db = cur.fetchall()
    productos_list = []
    for p in productos_db:
        productos_list.append({
            'nombre': p[0],
            'cantidad': int(p[1]) if p[1] else 0,
            'total': float(p[2]) if p[2] else 0
        })
    
    # Calcular ventas por hora - CORREGIDO
    ventas_hora = []
    for hora in range(24):
        ventas_hora.append({
            'hora': hora,
            'ventas': 0.0,
            'ordenes': 0
        })
    
    # Llenar datos reales de ventas por hora
    for venta in ventas_list:
        if venta['fecha_apertura']:
            try:
                if isinstance(venta['fecha_apertura'], datetime):
                    hora = venta['fecha_apertura'].hour
                else:
                    # Si es string, convertir a datetime
                    if isinstance(venta['fecha_apertura'], str):
                        fecha_obj = datetime.strptime(venta['fecha_apertura'], '%Y-%m-%d %H:%M:%S')
                        hora = fecha_obj.hour
                    else:
                        continue
                ventas_hora[hora]['ventas'] += venta['total']
                ventas_hora[hora]['ordenes'] += 1
            except (AttributeError, TypeError, ValueError) as e:
                print(f"Error procesando hora de venta: {e}")
                continue
    
    cur.close()
    conn.close()
    
    # Crear objeto estadísticas
    estadisticas = {
        'total_ordenes': total_ordenes,
        'total_ventas': total_ventas,
        'promedio_venta': promedio_venta
    }
    
    hoy = datetime.now()
    
    return render_template("ventas.html",
                         usuario=usuario_actual,
                         pedidos=ventas_list,  # El template usa 'pedidos' en lugar de 'ventas'
                         ventas=ventas_list,   # Mantener ambas por compatibilidad
                         productos=productos_list,
                         ventas_hora=ventas_hora,
                         total_ventas=total_ventas,
                         total_ordenes=total_ordenes,
                         estadisticas=estadisticas,
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin,
                         hoy=hoy,
                         ahora=datetime.now())

@app.route("/cerrar_caja", methods=["GET", "POST"])
@login_required
def cerrar_caja():
    """Cerrar turno de caja"""
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
            return redirect(url_for('cerrar_caja'))
        finally:
            cur.close()
            conn.close()
    
    cur.close()
    conn.close()
    
    return render_template("cerrar_caja.html",
                         usuario=usuario_actual,
                         turno=turno,
                         total_ventas_turno=total_ventas_turno,
                         monto_esperado=turno['monto_inicial'] + float(total_ventas_turno),
                         ahora=datetime.now())

# ==============================
# RUTA HISTORIAL DE CAJA (CORREGIDO)
# ==============================
@app.route("/historial_caja")
@login_required
def historial_caja():
    """Historial de turnos de caja"""
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
    
    # Calcular estadísticas
    if turnos_list:
        total_turnos = len(turnos_list)
        ventas_totales = sum(t['total_ventas'] for t in turnos_list)
        estadisticas = {
            'total_turnos': total_turnos,
            'ventas_totales': ventas_totales
        }
    else:
        estadisticas = {'total_turnos': 0, 'ventas_totales': 0}
    
    cur.close()
    conn.close()
    
    return render_template("historial_caja.html",
                         usuario=usuario_actual,
                         turnos=turnos_list,
                         estadisticas=estadisticas,
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin,
                         ahora=datetime.now())

# ==============================
# API PARA CREAR ORDEN
# ==============================
@app.route("/api/crear_orden", methods=["POST"])
@login_required
def api_crear_orden():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data"}), 400
        
        mesa_id = data.get('mesa_id')
        mozo_nombre = data.get('mozo_nombre', 'Mozo')
        items = data.get('items', [])
        observaciones = data.get('observaciones', '')
        
        if not mesa_id:
            return jsonify({"success": False, "message": "Mesa requerida"}), 400
        if not items:
            return jsonify({"success": False, "message": "Orden vacía"}), 400
        
        conn = get_db_connection()
        conn.autocommit = False
        cur = conn.cursor()
        
        try:
            cur.execute('SELECT numero FROM mesas WHERE id = %s', (mesa_id,))
            mesa_result = cur.fetchone()
            mesa_numero = mesa_result[0] if mesa_result else 0
            
            total = sum(item['precio_unitario'] * item['cantidad'] for item in items)
            dispositivo_origen = request.headers.get('User-Agent', 'Desconocido')[:50]
            
            cur.execute('INSERT INTO ordenes (mesa_id, mozo_nombre, observaciones, total, dispositivo_origen) VALUES (%s, %s, %s, %s, %s) RETURNING id', (mesa_id, mozo_nombre, observaciones, total, dispositivo_origen))
            orden_id = cur.fetchone()[0]
            
            for item in items:
                cur.execute('INSERT INTO orden_items (orden_id, producto_id, producto_nombre, cantidad, precio_unitario, observaciones, estado_item) VALUES (%s, %s, %s, %s, %s, %s, %s)', (orden_id, item['producto_id'], item['producto_nombre'], item['cantidad'], item['precio_unitario'], item.get('observaciones', ''), 'pendiente'))
                
                # Solo restar stock si no es comida
                cur.execute('SELECT tipo FROM productos WHERE id = %s', (item['producto_id'],))
                producto_tipo = cur.fetchone()
                if producto_tipo and producto_tipo[0] != 'comida':
                    cur.execute('UPDATE productos SET stock = stock - %s WHERE id = %s', (item['cantidad'], item['producto_id']))
            
            cur.execute('UPDATE mesas SET estado = %s WHERE id = %s', ('ocupada', mesa_id))
            
            conn.commit()
            
            # Enviar notificación al chef
            now = datetime.now()
            socketio.emit('nuevo_pedido_chef', {
                'pedido_id': orden_id, 
                'mesa_numero': mesa_numero, 
                'mozo_nombre': mozo_nombre,
                'total': total, 
                'items_count': len(items), 
                'dispositivo': dispositivo_origen,
                'timestamp': now.strftime('%H:%M:%S'),
                'fecha': now.strftime('%Y-%m-%d'),
                'items': items,
                'observaciones': observaciones,
                'urgente': any('urgente' in str(item.get('observaciones', '')).lower() for item in items)
            }, namespace='/chef')
            
            socketio.emit('nuevo_pedido_ws', {
                'pedido_id': orden_id, 
                'mesa_numero': mesa_numero, 
                'mozo_nombre': mozo_nombre,
                'total': total, 
                'items_count': len(items), 
                'dispositivo': dispositivo_origen,
                'timestamp': now.strftime('%H:%M:%S')
            })
            
            return jsonify({"success": True, "orden_id": orden_id, "mesa_numero": mesa_numero, "message": "Orden creada exitosamente"})
            
        except Exception as e:
            conn.rollback()
            print(f"Error creando orden: {e}")
            return jsonify({"success": False, "message": str(e)}), 500
        finally:
            cur.close()
            conn.close()
            
    except Exception as e:
        print(f"Error en api_crear_orden: {e}")
        return jsonify({"success": False, "message": "Error del servidor"}), 500

# ==============================
# OTRAS API PÚBLICAS
# ==============================
@app.route("/api/mesas")
def api_mesas():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT m.*, o.id as orden_id, CASE WHEN o.id IS NOT NULL THEN true ELSE false END as tiene_orden FROM mesas m LEFT JOIN ordenes o ON m.id = o.mesa_id AND o.estado = %s ORDER BY m.numero', ('abierta',))
        mesas_db = cur.fetchall()
        mesas_list = []
        for m in mesas_db:
            mesas_list.append({
                'id': m[0], 'numero': m[1], 'capacidad': m[2], 'estado': m[3],
                'ubicacion': m[4], 'orden_id': m[6], 'tiene_orden': m[7]
            })
        return jsonify(mesas_list)
    except Exception as e:
        print(f"Error obteniendo mesas: {e}")
        return jsonify([])
    finally:
        cur.close()
        conn.close()

@app.route("/api/categorias")
def api_categorias():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
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
        cur.close()
        conn.close()

@app.route("/api/productos")
def api_productos():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT p.id, p.codigo_barra, p.nombre, p.precio, p.stock, p.tipo, p.categoria_id, c.nombre as categoria_nombre FROM productos p LEFT JOIN categorias c ON p.categoria_id = c.id ORDER BY p.nombre')
        productos_db = cur.fetchall()
        productos_list = []
        for p in productos_db:
            # Convertir stock a entero
            stock_value = p[4]
            if stock_value is None:
                stock_int = 0
            else:
                try:
                    stock_int = int(stock_value)
                except (ValueError, TypeError):
                    stock_int = 0
            
            # Convertir precio a float
            precio_value = p[3]
            if precio_value is None:
                precio_float = 0.0
            else:
                try:
                    precio_float = float(precio_value)
                except (ValueError, TypeError):
                    precio_float = 0.0
            
            productos_list.append({
                'id': p[0], 
                'codigo_barra': p[1], 
                'nombre': p[2],
                'precio': precio_float,  # Convertido a float
                'stock': stock_int,      # Convertido a int
                'tipo': p[5] if len(p) > 5 else 'producto',
                'categoria_id': p[6], 
                'categoria_nombre': p[7] if p[7] else 'Sin categoría'
            })
        return jsonify(productos_list)
    except Exception as e:
        print(f"Error obteniendo productos: {e}")
        return jsonify([])
    finally:
        cur.close()
        conn.close()

@app.route("/api/ordenes_activas")
def api_ordenes_activas():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT o.id, o.mesa_id, m.numero as mesa_numero, o.mozo_nombre, o.total, o.fecha_apertura, o.estado, COUNT(oi.id) as items_count FROM ordenes o JOIN mesas m ON o.mesa_id = m.id LEFT JOIN orden_items oi ON o.id = oi.orden_id WHERE o.estado IN (%s, %s, %s) GROUP BY o.id, m.numero ORDER BY o.fecha_apertura DESC', ('abierta', 'proceso', 'listo'))
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
        cur.close()
        conn.close()

@app.route("/api/notificaciones_mozo")
def api_notificaciones_mozo():
    """API pública para notificaciones"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
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
        cur.close()
        conn.close()

@app.route("/api/orden_detalle/<int:orden_id>")
@login_required
def api_orden_detalle(orden_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            SELECT o.*, m.numero as mesa_numero 
            FROM ordenes o 
            JOIN mesas m ON o.mesa_id = m.id 
            WHERE o.id = %s
        ''', (orden_id,))
        orden_db = cur.fetchone()
        
        if not orden_db:
            return jsonify({"success": False, "message": "Orden no encontrada"}), 404
        
        orden = {
            'id': orden_db[0], 'mesa_id': orden_db[1], 'mesa_numero': orden_db[9],
            'mozo_nombre': orden_db[2], 'estado': orden_db[3], 'observaciones': orden_db[4],
            'total': float(orden_db[5]) if orden_db[5] else 0,
            'fecha_apertura': orden_db[6].strftime('%Y-%m-%d %H:%M:%S') if orden_db[6] else ''
        }
        
        cur.execute('''
            SELECT id, producto_id, producto_nombre, cantidad, 
                   precio_unitario, observaciones 
            FROM orden_items 
            WHERE orden_id = %s 
            ORDER BY id
        ''', (orden_id,))
        items_db = cur.fetchall()
        
        items = []
        for item in items_db:
            items.append({
                'id': item[0], 'producto_id': item[1], 'producto_nombre': item[2],
                'cantidad': item[3], 'precio_unitario': float(item[4]) if item[4] else 0,
                'observaciones': item[5]
            })
        
        orden['items'] = items
        return jsonify(orden)
        
    except Exception as e:
        print(f"Error obteniendo orden: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route("/api/cerrar_orden/<int:orden_id>", methods=["POST"])
@login_required
def api_cerrar_orden(orden_id):
    """Cerrar orden y liberar mesa"""
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

# ==============================
# API PARA ABRIR TURNO DE CAJA
# ==============================
@app.route("/api/abrir_turno", methods=["POST"])
@login_required
def api_abrir_turno():
    """API para abrir turno de caja"""
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

# ==============================
# API COMPATIBILIDAD
# ==============================
@app.route("/api/pedidos_cocina")
def api_pedidos_cocina():
    """Alias para compatibilidad"""
    return redirect(url_for('api_pedidos_cocina_comidas'))

@app.route("/logout")
def logout():
    session.clear()
    flash('Sesión cerrada correctamente', 'info')
    return redirect(url_for('chef'))

# ==============================
# RUTAS PARA GESTIÓN DE MESAS
# ==============================
@app.route("/abrir_mesa/<int:mesa_id>")
@login_required
def abrir_mesa(mesa_id):
    """Abrir una mesa (cambiar estado a disponible)"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('SELECT * FROM mesas WHERE id = %s', (mesa_id,))
        mesa = cur.fetchone()
        
        if not mesa:
            flash('Mesa no encontrada', 'danger')
            return redirect(url_for('mesas'))
        
        cur.execute('UPDATE mesas SET estado = %s WHERE id = %s', ('disponible', mesa_id))
        
        cur.execute('SELECT id FROM ordenes WHERE mesa_id = %s AND estado IN (%s, %s, %s)', 
                   (mesa_id, 'abierta', 'proceso', 'listo'))
        orden_activa = cur.fetchone()
        
        if orden_activa:
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

@app.route("/ocupar_mesa/<int:mesa_id>")
@login_required
def ocupar_mesa(mesa_id):
    """Ocupar una mesa (cambiar estado a ocupada)"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('SELECT * FROM mesas WHERE id = %s', (mesa_id,))
        mesa = cur.fetchone()
        
        if not mesa:
            flash('Mesa no encontrada', 'danger')
            return redirect(url_for('mesas'))
        
        cur.execute('UPDATE mesas SET estado = %s WHERE id = %s', ('ocupada', mesa_id))
        conn.commit()
        flash(f'Mesa #{mesa[1]} ocupada exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        print(f"Error ocupando mesa: {e}")
        flash(f'Error al ocupar mesa: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('mesas'))

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
# INICIO DEL SERVIDOR
# ==============================
if __name__ == "__main__":
    import sys
    import webbrowser
    import threading

    # Crear tablas solo al iniciar el servidor
    print("🔄 Creando tablas de base de datos...")
    create_tables()
    reparar_productos()
    print("✅ Base de datos inicializada")

    def abrir_navegador():
        webbrowser.open("http://127.0.0.1:5000/login")

    # Solo abrir navegador si es un .exe
    if getattr(sys, "frozen", False):
        threading.Timer(2, abrir_navegador).start()

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=False,
        allow_unsafe_werkzeug=False,
        use_reloader=False
    )
