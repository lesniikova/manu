import json
import logging
import random
import requests
import jwt
import pika
from bottle import Bottle, run, request, response, HTTPError
from bottle_cors_plugin import cors_plugin
from bson.objectid import ObjectId
from pymongo import MongoClient
import datetime

app = Bottle()

SECRET_KEY = 'nekaSkrivnost'
ALGORITHM = 'HS256'


@app.hook('after_request')
def enable_cors():
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'PUT, POST, GET, OPTION, DELETE'
    response.headers['Access-Control-Allow-Headers'] = '*'


@app.route('/', method='OPTIONS')
@app.route('/<path:path>', method='OPTIONS')
def options_handler(path=None):
    return


def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPError(401, 'Token has expired')
    except jwt.InvalidTokenError:
        raise HTTPError(401, 'Invalid token')


@app.route('/menu/protected', method='GET')
def protected_route():
    token = request.headers.get('Authorization')
    if not token:
        raise HTTPError(401, 'Token is missing')

    try:
        token = token.split()[1]
        data = verify_token(token)
        user_id = data.get('sub')
        name = data.get('name')
        return {'message': 'Access granted', 'user_id': user_id, 'name': name}
    except HTTPError as e:
        raise e
    except Exception as e:
        raise HTTPError(500, 'Internal server error')


client = MongoClient('mongodb://mongo:27017/menu-service')
db = client['menu-service']
menu_collection = db['menu']
counter_collection = db['counters']

app_name = 'menu-service'

amqp_url = 'amqp://student:student123@studentdocker.informatika.uni-mb.si:5672/'
exchange_name = 'UPP-2'
queue_name = 'UPP-2'


def get_next_sequence_value(sequence_name):
    counter = counter_collection.find_one_and_update(
        {'_id': sequence_name},
        {'$inc': {'value': 1}},
        upsert=True,
        return_document=True
    )
    return counter['value']


def json_encoder(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj


@app.route('/menu/all', method='GET')
def get_all_dishes():
    url = f"http://py-api:5050/posodobi"
    payload = {
        "klicanaStoritev": "/menu/all"
    }
    response = requests.post(url, json=payload)

    correlation_id = request.headers.get('X-Correlation-ID')
    response.headers['Access-Control-Allow-Origin'] = '*'  # Allow requests from any origin
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'
    data = list(menu_collection.find())
    menu_json = json.dumps(data, default=json_encoder)
    message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
        datetime.datetime.now(), request.url, correlation_id, app_name,
        '*Klic storitve GET menu all*'))
    connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
    channel = connection.channel()

    channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
    channel.queue_declare(queue=queue_name)
    channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

    channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

    connection.close()

    return menu_json
    pass


@app.route('/menu/<id>', method='GET')
def get_dish(id):
    url = f"http://py-api:5050/posodobi"
    payload = {
        "klicanaStoritev": "/menu/<id>"
    }
    response = requests.post(url, json=payload)
    correlation_id = str(random.randint(1, 99999))
    dish = menu_collection.find_one({'id': int(id)})
    if dish:
        message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
            datetime.datetime.now(), request.url, correlation_id, app_name,
            '*Klic storitve GET menu one*'))
        connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        channel = connection.channel()

        channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

        channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

        connection.close()
    else:
        return {'message': 'Dish not found'}


@app.route('/menu/create', method='POST')
def add_dish():
    url = f"http://py-api:5050/posodobi"
    payload = {
        "klicanaStoritev": "/menu/create"
    }
    response = requests.post(url, json=payload)

    correlation_id = str(random.randint(1, 99999))
    dish_data = request.json
    name = dish_data.get('name')
    price = dish_data.get('price')
    category = dish_data.get('category')
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'

    if name and price:
        dish = {
            'id': get_next_sequence_value('id'),
            'name': name,
            'price': price,
            'category': category
        }
        dish_id = menu_collection.insert_one(dish).inserted_id
        message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
            datetime.datetime.now(), request.url, correlation_id, app_name,
            '*Klic storitve POST menu create*'))
        connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        channel = connection.channel()

        channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

        channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

        connection.close()
        return {
            'message': 'Dish added successfully',
            'dish_id': str(dish_id)
        }
    else:
        return {'message': 'Invalid dish data'}


@app.route('/menu/<id>', method='PUT')
def update_dish(id):
    url = f"http://py-api:5050/posodobi"
    payload = {
        "klicanaStoritev": "/menu/<id>"
    }
    response = requests.post(url, json=payload)

    correlation_id = str(random.randint(1, 99999))
    dish_data = request.json
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'

    updated_dish = menu_collection.update_one({'id': int(id)}, {'$set': dish_data})
    if updated_dish.modified_count > 0:
        message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
            datetime.datetime.now(), request.url, correlation_id, app_name,
            '*Klic storitve PUT menu item*'))
        connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        channel = connection.channel()

        channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

        channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

        connection.close()
        return {'message': 'Dish updated successfully'}
    else:
        return {'message': 'Dish not found'}


@app.route('/menu/<id>', method='DELETE')
def delete_dish(id):
    url = f"http://py-api:5050/posodobi"
    payload = {
        "klicanaStoritev": "/menu/<id>"
    }
    response = requests.post(url, json=payload)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'
    correlation_id = str(random.randint(1, 99999))
    deleted_dish = menu_collection.delete_one({'id': int(id)})
    if deleted_dish.deleted_count > 0:
        message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
            datetime.datetime.now(), request.url, correlation_id, app_name,
            '*Klic storitve DELETE menu item*'))
        connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        channel = connection.channel()

        channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

        channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

        connection.close()
        return {'message': 'Dish deleted successfully'}
    else:
        return {'message': 'Dish not found'}


@app.route('/menu/<id>/order', method='POST')
def order_dish(id):
    url = f"http://py-api:5050/posodobi"
    payload = {
        "klicanaStoritev": "/menu/<id>/order"
    }
    response = requests.post(url, json=payload)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'
    correlation_id = str(random.randint(1, 99999))
    message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
        datetime.datetime.now(), request.url, correlation_id, app_name,
        '*Klic storitve POST order item*'))
    connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
    channel = connection.channel()

    channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
    channel.queue_declare(queue=queue_name)
    channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

    channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

    connection.close()

    return {'message': 'Order placed for dish with ID: ' + id}


@app.route('/menu/category/<category>', method='GET')
def get_dishes_by_category(category):
    url = f"http://py-api:5050/posodobi"
    payload = {
        "klicanaStoritev": "/menu/category/<category>"
    }
    response = requests.post(url, json=payload)
    correlation_id = str(random.randint(1, 99999))
    dishes = menu_collection.find({'category': category})
    dishes_list = [dish for dish in dishes]

    menu_json = json.dumps(dishes_list, default=json_encoder)
    message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
        datetime.datetime.now(), request.url, correlation_id, app_name,
        '*Klic storitve GET category*'))
    connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
    channel = connection.channel()

    channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
    channel.queue_declare(queue=queue_name)
    channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

    channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

    connection.close()


    return menu_json


@app.route('/menu/random', method='GET')
def get_random_dish():
    url = f"http://py-api:5050/posodobi"
    payload = {
        "klicanaStoritev": "/menu/random"
    }
    response = requests.post(url, json=payload)
    correlation_id = str(random.randint(1, 99999))
    all_dishes = menu_collection.find()
    dishes_list = [dish for dish in all_dishes]

    if dishes_list:
        random_dish = random.choice(dishes_list)
        random_dish_json = json.dumps(random_dish, default=json_encoder)
        message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
            datetime.datetime.now(), request.url, correlation_id, app_name,
            '*Klic storitve GET random*'))
        connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        channel = connection.channel()

        channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

        channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

        connection.close()
        return random_dish_json
    else:
        return json.dumps({'message': 'No dishes found in the menu'})


if __name__ == '__main__':
    run(app, host="0.0.0.0", port=8000)
channel.close()
