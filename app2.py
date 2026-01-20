# ==============================
# APP POS - VERSIÓN SIMPLIFICADA
# ==============================
import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from datetime import datetime
import hashlib

app = Flask(__name__)
app.secret_key = 'clave_secreta_pos_2024_sistema_login'

# ==============================
# RUTAS PRINCIPALES
# ==============================
@app.route("/")
def index():
    return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if 'user_id' in session:
        return redirect_based_on_role(session.get('rol', 'cajero'))
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        usuarios = {
            'admin': {'password': 'admin123', 'nombre': 'Administrador', 'rol': 'admin'},
            'mozo': {'password': 'mozo123', 'nombre': 'Mozo Principal', 'rol': 'mozo'},
            'chef': {'password': 'chef123', 'nombre': 'Chef Principal', 'rol': 'chef'},
            'cajero': {'password': 'cajero123', 'nombre': 'Cajero Principal', 'rol': 'cajero'}
        }
        
        if username in usuarios and usuarios[username]['password'] == password:
            session['user_id'] = 1
            session['username'] = username
            session['nombre'] = usuarios[username]['nombre']
            session['rol'] = usuarios[username]['rol']
            
            flash(f'Bienvenido {usuarios[username]["nombre"]}!', 'success')
            return redirect_based_on_role(usuarios[username]['rol'])
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    
    return render_template("login.html", ahora=datetime.now())

def redirect_based_on_role(rol):
    if rol == 'chef':
        return redirect(url_for('chef'))
    elif rol == 'mozo':
        return redirect(url_for('mesas'))
    elif rol == 'admin':
        return redirect(url_for('productos'))
    else:
        return redirect(url_for('caja'))

def get_usuario_actual():
    if 'user_id' in session:
        return {
            'id': session['user_id'],
            'username': session.get('username'),
            'nombre': session.get('nombre'),
            'rol': session.get('rol')
        }
    return None

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Debes iniciar sesión primero', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==============================
# PANELES PRINCIPALES
# ==============================
@app.route("/chef")
@login_required
def chef():
    usuario_actual = get_usuario_actual()
    return render_template("chef.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/caja")
@login_required
def caja():
    usuario_actual = get_usuario_actual()
    return render_template("caja.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/mesas")
@login_required
def mesas():
    usuario_actual = get_usuario_actual()
    return render_template("mesas.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/productos")
@login_required
def productos():
    usuario_actual = get_usuario_actual()
    return render_template("productos.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/ordenes")
@login_required
def ordenes():
    usuario_actual = get_usuario_actual()
    return render_template("ordenes.html", usuario=usuario_actual, ahora=datetime.now())

# ==============================
# APIS SIMULADAS (SIN BASE DE DATOS)
# ==============================
@app.route("/api/mesas")
@login_required
def api_mesas():
    # Datos de ejemplo para mesas
    mesas_ejemplo = [
        {'id': 1, 'numero': 1, 'capacidad': 4, 'estado': 'disponible', 'ubicacion': 'Salón principal'},
        {'id': 2, 'numero': 2, 'capacidad': 6, 'estado': 'ocupada', 'ubicacion': 'Terraza'},
        {'id': 3, 'numero': 3, 'capacidad': 2, 'estado': 'disponible', 'ubicacion': 'Interior'},
        {'id': 4, 'numero': 4, 'capacidad': 8, 'estado': 'reservada', 'ubicacion': 'Salón VIP'},
    ]
    return jsonify(mesas_ejemplo)

@app.route("/api/productos")
@login_required
def api_productos():
    # Datos de ejemplo para productos
    productos_ejemplo = [
        {'id': 1, 'nombre': 'Bife de Chorizo', 'precio': 4500.00, 'stock': 10, 'tipo': 'comida'},
        {'id': 2, 'nombre': 'Milanesa Napolitana', 'precio': 3800.00, 'stock': 15, 'tipo': 'comida'},
        {'id': 3, 'nombre': 'Pizza Mozzarella', 'precio': 3200.00, 'stock': 8, 'tipo': 'comida'},
        {'id': 4, 'nombre': 'Coca Cola 500ml', 'precio': 800.00, 'stock': 50, 'tipo': 'bebida'},
        {'id': 5, 'nombre': 'Agua Mineral', 'precio': 500.00, 'stock': 30, 'tipo': 'bebida'},
        {'id': 6, 'nombre': 'Cerveza Artesanal', 'precio': 1200.00, 'stock': 25, 'tipo': 'bebida'},
    ]
    return jsonify(productos_ejemplo)

@app.route("/api/pedidos_cocina_comidas")
@login_required
def api_pedidos_cocina_comidas():
    # Datos de ejemplo para pedidos en cocina
    pedidos_ejemplo = [
        {
            'id': 101,
            'mesa_numero': 2,
            'mozo_nombre': 'Juan Pérez',
            'estado_orden': 'proceso',
            'fecha_apertura': '19:30',
            'total': 15600.00,
            'items': [
                {'id': 1001, 'producto_nombre': 'Bife de Chorizo', 'cantidad': 2, 'estado_item': 'listo', 'observaciones': 'Punto medio'},
                {'id': 1002, 'producto_nombre': 'Pizza Mozzarella', 'cantidad': 1, 'estado_item': 'proceso', 'observaciones': ''},
                {'id': 1003, 'producto_nombre': 'Coca Cola 500ml', 'cantidad': 3, 'estado_item': 'listo', 'observaciones': ''},
            ],
            'estadisticas': {'pendientes': 0, 'proceso': 1, 'listos': 2, 'total': 3}
        },
        {
            'id': 102,
            'mesa_numero': 4,
            'mozo_nombre': 'María González',
            'estado_orden': 'abierta',
            'fecha_apertura': '19:45',
            'total': 8600.00,
            'items': [
                {'id': 1004, 'producto_nombre': 'Milanesa Napolitana', 'cantidad': 2, 'estado_item': 'pendiente', 'observaciones': 'Sin papas'},
                {'id': 1005, 'producto_nombre': 'Cerveza Artesanal', 'cantidad': 1, 'estado_item': 'pendiente', 'observaciones': 'Fría'},
            ],
            'estadisticas': {'pendientes': 2, 'proceso': 0, 'listos': 0, 'total': 2}
        }
    ]
    return jsonify(pedidos_ejemplo)

@app.route("/api/actualizar_item_estado", methods=["POST"])
@login_required
def api_actualizar_item_estado():
    # Simular actualización de estado
    data = request.get_json()
    item_id = data.get('item_id')
    nuevo_estado = data.get('estado')
    
    if not item_id or not nuevo_estado:
        return jsonify({"success": False, "message": "Faltan datos"}), 400
    
    return jsonify({
        "success": True, 
        "message": f"Item {item_id} actualizado a {nuevo_estado}",
        "timestamp": datetime.now().strftime('%H:%M:%S')
    })

@app.route("/api/crear_orden", methods=["POST"])
@login_required
def api_crear_orden():
    # Simular creación de orden
    data = request.get_json()
    mesa_id = data.get('mesa_id')
    items = data.get('items', [])
    
    if not mesa_id or not items:
        return jsonify({"success": False, "message": "Datos incompletos"}), 400
    
    total = sum(item.get('precio_unitario', 0) * item.get('cantidad', 0) for item in items)
    
    return jsonify({
        "success": True, 
        "orden_id": 999,
        "mesa_numero": mesa_id,
        "total": total,
        "message": "Orden creada exitosamente (modo demo)"
    })

# ==============================
# RUTAS ADICIONALES
# ==============================
@app.route("/logout")
def logout():
    session.clear()
    flash('Sesión cerrada correctamente', 'info')
    return redirect(url_for('login'))

@app.route("/api/pedidos_cocina")
def api_pedidos_cocina():
    return redirect(url_for('api_pedidos_cocina_comidas'))

# ==============================
# MANEJO DE ERRORES
# ==============================
@app.errorhandler(404)
def pagina_no_encontrada(e):
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>404 - Página no encontrada</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            h1 { color: #e74c3c; }
            a { color: #3498db; text-decoration: none; }
        </style>
    </head>
    <body>
        <h1>404 - Página no encontrada</h1>
        <p>La página que buscas no existe.</p>
        <a href='/login'>← Volver al login</a>
    </body>
    </html>
    ''', 404

@app.errorhandler(500)
def error_servidor(e):
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>500 - Error del servidor</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            h1 { color: #e74c3c; }
            a { color: #3498db; text-decoration: none; }
        </style>
    </head>
    <body>
        <h1>500 - Error del servidor</h1>
        <p>Algo salió mal en el servidor.</p>
        <a href='/login'>← Volver al login</a>
    </body>
    </html>
    ''', 500

# ==============================
# INICIO DEL SERVIDOR
# ==============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
