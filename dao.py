from pymongo import MongoClient
import random
import os
from dotenv import load_dotenv

load_dotenv()
mongo_url = os.getenv('MONGO_URL')
mongo_db = os.getenv('MONDO_DB_NAME')
mongo_collection = os.getenv('MONGO_COLLECTION_NAME')

client = MongoClient(mongo_url)
db = client[mongo_db]
rooms_collection = db[mongo_collection]


async def create_room_mongo(description, admin_id, admin_name):
    while True:
        room_id = random.randint(1000, 9999)
        if not await check_room_number(room_id):
            break
    room = {
        "room_id": str(room_id),
        "participants": {str(admin_id): admin_name},  # Необходимо указать имя администратора
        "description": description,
        "admin": str(admin_id)
    }
    rooms_collection.insert_one(room)
    return room_id


async def check_room_number(room_id):
    existing_room = rooms_collection.find_one({"room_id": str(room_id)})
    return existing_room is not None


async def add_participant(room_id, user_id, user_name):
    rooms_collection.update_one(
        {"room_id": room_id},
        {"$set": {f"participants.{user_id}": user_name}}
    )


async def get_room_info(room_id):
    return rooms_collection.find_one({"room_id": room_id})


async def find_user_rooms(user_id):
    return rooms_collection.find({"$or": [{"admin": user_id}, {"participants." + user_id: {"$exists": True}}]})


async def find_rooms_by_admin(user_id):
    return rooms_collection.find({"admin": user_id}, {"room_id": 1})


async def find_rooms_with_multiple_participants(admin_id):
    return rooms_collection.find(
        {"admin": admin_id, "participants": {"$not": {"$size": 1}}},
        {"room_id": 1}
    )


async def delete_room_from_db(room_id):
    return rooms_collection.delete_one({"room_id": room_id})


async def count_user_rooms_with_multiple_participants(user_id):
    return rooms_collection.count_documents({"admin": user_id})
