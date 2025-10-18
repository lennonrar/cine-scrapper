from src.redis import RedisCache


def init_redis():
    cache = RedisCache()
    response = cache.client.ping()
    print(f"Initialized Redis Cache: {response}")
    return cache
