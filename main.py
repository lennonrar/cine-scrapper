from src.movies.services.cinemateca import get_movies_cinemateca


def main():
    movies = get_movies_cinemateca()
    print('*' * 20)

    for movie in movies:
        print(movie)


if __name__ == '__main__':
    main()
    print('End of execution')
