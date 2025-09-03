from pymongo import MongoClient

# TODO add environment variables for auth config here. Currently no auth
client = MongoClient("mongodb://localhost:27017")
db = client.academicworld


def get_or_create_session(session_id):
    return db.favorites.find_one_and_update(
        {"session_id": session_id},
        {"$setOnInsert": {"professors": [], "universities": [], "topics": []}},
        upsert=True,
        return_document=True,
    )


def add_favorite(session_id, category, item):
    db.favorites.update_one({"session_id": session_id}, {"$addToSet": {category: item}})


def remove_favorite(session_id, category, item):
    db.favorites.update_one({"session_id": session_id}, {"$pull": {category: item}})


def get_favorites(session_id):
    doc = db.favorites.find_one({"session_id": session_id})
    return doc if doc else {"professors": [], "universities": [], "topics": []}
