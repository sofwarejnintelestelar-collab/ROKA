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
# CONEXIÓN A BASE DE DATOS (CORREGIDO PARA RENDER)
# ==============================
def get_db_connection():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # Render usa DATABASE_URL en formato postgresql://...
        return psycopg2.connect(database_url, sslmode="require")
    else:
        # Configuración local (para desarrollo)
        return psycopg2.connect(
            host="localhost",
            port="5432",
            database="roka",
            user="postgres",
            password="pm"
        )

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
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
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
        
        # Verificar si ya hay datos iniciales
        cur.execute("SELECT COUNT(*) FROM categorias")
        if cur.fetchone()[0] == 0:
            print("📝 Insertando categorías por defecto...")
            categorias_default = ['ENTRADAS', 'PICADAS', 'EMPANADAS', 'MINUTAS', 'GUARNICIONES', 
                                 'PASTAS', 'SALSAS', 'PIZZAS', 'PLATOS ESPECIALES', 'POSTRES', 'HELADOS']
            for nombre in categorias_default:
                try:
                    cur.execute("INSERT INTO categorias (nombre) VALUES (%s)", (nombre,))
                except:
                    continue
        
        cur.execute("SELECT COUNT(*) FROM mesas")
        if cur.fetchone()[0] == 0:
            print("📝 Insertando mesas por defecto...")
            for i in range(1, 11):
                try:
                    cur.execute("INSERT INTO mesas (numero, capacidad) VALUES (%s, %s)", (i, 4))
                except:
                    continue
        
        cur.execute("SELECT COUNT(*) FROM usuarios WHERE username = 'admin'")
        if cur.fetchone()[0] == 0:
            print("📝 Insertando usuarios por defecto...")
            password_hash = hashlib.sha256('admin123'.encode()).hexdigest()
            try:
                cur.execute('INSERT INTO usuarios (username, password_hash, nombre, email, rol) VALUES (%s, %s, %s, %s, %s)', 
                           ('admin', password_hash, 'Administrador', 'admin@sistema.com', 'admin'))
            except:
                pass
            
            try:
                cur.execute('INSERT INTO usuarios (username, password_hash, nombre, email, rol) VALUES (%s, %s, %s, %s, %s)', 
                           ('mozo', hashlib.sha256('mozo123'.encode()).hexdigest(), 'Mozo Principal', 'mozo@sistema.com', 'mozo'))
            except:
                pass
            
            try:
                cur.execute('INSERT INTO usuarios (username, password_hash, nombre, email, rol) VALUES (%s, %s, %s, %s, %s)', 
                           ('chef', hashlib.sha256('chef123'.encode()).hexdigest(), 'Chef Principal', 'chef@sistema.com', 'chef'))
            except:
                pass
            
            try:
                cur.execute('INSERT INTO usuarios (username, password_hash, nombre, email, rol) VALUES (%s, %s, %s, %s, %s)', 
                           ('cajero', hashlib.sha256('cajero123'.encode()).hexdigest(), 'Cajero Principal', 'cajero@sistema.com', 'cajero'))
            except:
                pass
        
        conn.commit()
        print("✅ Tablas verificadas/creadas exitosamente")
        
    except Exception as e:
        print(f"⚠️  Advertencia al crear tablas (puede que ya existan): {e}")
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

# ==============================
# FUNCIÓN PARA REPARAR PRODUCTOS MAL CARGADOS (CORREGIDO)
# ==============================
def reparar_productos():
    """Función para reparar productos con datos intercambiados"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            # 1. Agregar columna tipo si no existe
            try:
                cur.execute("ALTER TABLE productos ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) DEFAULT 'producto'")
                conn.commit()
            except Exception as e:
                print(f"ℹ️  La columna 'tipo' ya existe o no se pudo agregar: {e}")
            
            # 2. Buscar productos donde el nombre es un número (precio mal puesto)
            # CORRECCIÓN: Escapar correctamente el punto en la regex
            cur.execute(r"SELECT id, nombre, codigo_barra, precio FROM productos WHERE nombre ~ '^[0-9]+\.?[0-9]*$'")
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
            print(f"⚠️  Advertencia al reparar productos: {e}")
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        print(f"⚠️  No se pudo conectar para reparar productos: {e}")

# Solo ejecutar create_tables() si estamos en el main
# NO ejecutar automáticamente en importación

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
        print(f"❌ Error en login: {e}")
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
# RUTAS PRINCIPALES - MODIFICADO: AHORA INICIA DESDE LOGIN
# ==============================
@app.route("/")
def index():
    """Página principal - Redirige a LOGIN en lugar de chef"""
    return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    """Login para sistema POS - Página principal"""
    if 'user_id' in session:
        usuario_actual = get_usuario_actual()
        if usuario_actual:
            flash(f'Ya estás logueado como {usuario_actual["nombre"]}', 'info')
            
            # Redirigir según rol
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
            
            # Redirigir según rol
            if usuario['rol'] == 'chef':
                print(f"👨‍🍳 Chef {usuario['nombre']} inició sesión")
                return redirect(url_for('chef'))
            elif usuario['rol'] == 'mozo':
                return redirect(url_for('ordenes'))
            elif usuario['rol'] == 'admin':
                return redirect(url_for('productos'))
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
    
    try:
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
    except Exception as e:
        print(f"Error en caja: {e}")
        return render_template("caja_sin_turno.html", 
                             usuario=usuario_actual, 
                             ahora=datetime.now(),
                             ordenes_abiertas=[])

# ==============================
# PANEL DEL CHEF - ACCESO SOLO PARA CHEFS LOGUEADOS
# ==============================
@app.route("/chef")
@login_required
def chef():
    """Panel del chef - Requiere login y rol de chef"""
    usuario_actual = get_usuario_actual()
    
    # Verificar si el usuario tiene rol de chef
    if usuario_actual['rol'] != 'chef':
        flash('Acceso restringido. Se requiere rol de chef.', 'danger')
        return redirect(url_for('login'))
    
    print(f"👨‍🍳 Chef {usuario_actual['nombre']} accedió al panel")
    
    return render_template("chef.html", 
                         usuario=usuario_actual,
                         ahora=datetime.now())

# ==============================
# API ENDPOINTS PÚBLICOS PARA CHEF (solo para chefs)
# ==============================
@app.route("/api/pedidos_cocina_comidas")
@login_required
def api_pedidos_cocina_comidas():
    """API para mostrar solo comidas en la cocina - requiere login"""
    usuario_actual = get_usuario_actual()
    
    # Solo chefs pueden acceder a esta API
    if usuario_actual['rol'] != 'chef':
        return jsonify({"error": "Acceso no autorizado"}), 403
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
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
        
        cur.close()
        conn.close()
        
        return jsonify(pedidos_list)
    except Exception as e:
        print(f"Error obteniendo pedidos cocina comidas: {e}")
        return jsonify([])

@app.route("/api/actualizar_item_estado", methods=["POST"])
@login_required
def api_actualizar_item_estado():
    """API para actualizar estado de items - requiere login"""
    usuario_actual = get_usuario_actual()
    
    # Solo chefs pueden actualizar estados
    if usuario_actual['rol'] != 'chef':
        return jsonify({"success": False, "message": "Acceso no autorizado"}), 403
    
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
    
    try:
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
    except Exception as e:
        print(f"Error en productos: {e}")
        flash('Error al cargar productos', 'danger')
        return render_template("productos.html", 
                             usuario=usuario_actual,
                             productos=[],
                             categorias=[],
                             proveedores=[],
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
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
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
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                flash(f'El código de barras "{codigo_barra}" ya existe', 'danger')
            else:
                flash(f'Error al crear producto: {str(e)}', 'danger')
            return redirect(url_for('crear_producto'))
        finally:
            try:
                cur.close()
                conn.close()
            except:
                pass
    
    # GET request - mostrar formulario
    try:
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
    except Exception as e:
        print(f"Error cargando categorías/proveedores: {e}")
        flash('Error al cargar datos del formulario', 'danger')
        return redirect(url_for('productos'))

# ==============================
# RUTAS PARA ORDENES
# ==============================
@app.route("/ordenes")
@login_required
def ordenes():
    usuario_actual = get_usuario_actual()
    return render_template("ordenes.html", usuario=usuario_actual, ahora=datetime.now())

# ==============================
# RUTAS PARA MESAS
# ==============================
@app.route("/mesas")
@login_required
def mesas():
    usuario_actual = get_usuario_actual()
    return render_template("mesas.html", usuario=usuario_actual, ahora=datetime.now())

# ==============================
# OTRAS RUTAS BÁSICAS
# ==============================
@app.route("/categorias")
@login_required
def categorias():
    usuario_actual = get_usuario_actual()
    return render_template("categorias.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/proveedores")
@login_required
def proveedores():
    usuario_actual = get_usuario_actual()
    return render_template("proveedores.html", usuario=usuario_actual, ahora=datetime.now())

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

@app.route("/cerrar_caja")
@login_required
def cerrar_caja():
    usuario_actual = get_usuario_actual()
    return render_template("cerrar_caja.html", usuario=usuario_actual, ahora=datetime.now())

# ==============================
# APIS BÁSICAS
# ==============================
@app.route("/api/mesas")
def api_mesas():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
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
                'precio': precio_float,
                'stock': stock_int,
                'tipo': p[5] if len(p) > 5 else 'producto',
                'categoria_id': p[6], 
                'categoria_nombre': p[7] if p[7] else 'Sin categoría'
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

@app.route("/api/ordenes_activas")
@login_required
def api_ordenes_activas():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
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
# INICIO DEL SERVIDOR PARA RENDER
# ==============================
if __name__ == "__main__":
    # Solo crear tablas si estamos ejecutando directamente
    print("🚀 Iniciando aplicación...")
    try:
        create_tables()
        reparar_productos()
    except Exception as e:
        print(f"⚠️  Advertencia durante inicialización: {e}")
    
    import os
    port = int(os.environ.get("PORT", 5000))
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        allow_unsafe_werkzeug=False,
        use_reloader=False
    )
