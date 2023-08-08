from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from flask_paginate import Pagination, get_page_parameter
from flask import Flask, jsonify
from flask import request, render_template
import difflib
import random
import psycopg2
import json

app = Flask(__name__)

app.config['SECRET_KEY'] = 'secret'  # Replace with a random secret key

display_ids = []
with open('display_ids.json') as f:
    display_ids = json.load(f)

table_title_ids = dict()
with open('table_title_ids.json') as f:
    table_title_ids = json.load(f)

initial_results = []
with open('initial_results.json') as f:
    initial_results = json.load(f)

BOOK_DESCRIPTION_COLUMNS = ['id', 'title', 'description','authors']
BOOK_RATINGS_COLUMNS = ['id', 'title', 'profilename', 'score','review']
BOOK_RATINGS1_COLUMNS = ['id', 'title', 'profilename', 'score']
BOOK_RATINGS2_COLUMNS = ['id', 'review']

# Global database connection
db_connection = None
book_count = None
latest_reviews = []
current_review_index = 0
DEFAULT_PAGE_SIZE = 10

REVIEW_COUNT = None
BOOK_IDS = []
BOOK_TITLES = []
BOOK_TITLE_ID = {}
BOOK_ID_TITLE = {}

MIN_BOOK_RATINGS_ID = 1
MAX_BOOK_RATINGS_ID = 2999999

def init_db():
    global db_connection
    db_connection = psycopg2.connect(
        dbname="postgres",
        user="postgres",
        password="postgres",
        host="book-db1.cwxo48b9errn.us-east-1.rds.amazonaws.com",
        port="5432"
    )

def execute_query(query, parameters=None):
    with db_connection.cursor() as cursor:
        if parameters:
            cursor.execute(query, parameters)
        else:
            cursor.execute(query)
        # For SELECT statements
        if query.strip().upper().startswith("SELECT"):
            return cursor.fetchall()

def get_cached_book_count():
    global book_count
    book_count = 209356
    return book_count

def get_cached_review_count():
    global REVIEW_COUNT
    REVIEW_COUNT = 8999999
    return REVIEW_COUNT
    

@app.route('/')
def index():
    total_books = get_cached_book_count()
    total_reviews = get_cached_review_count()
    latest_reviews = get_display_reviews(limit=10)  # fetches the latest 10 reviews
    return render_template('index.html', total_books=total_books, total_reviews=total_reviews, latest_reviews=latest_reviews)

@app.route('/get_initial_reviews')
def get_initial_review():
    global latest_reviews
    if len(latest_reviews) == 0:
        fetch_initial_reviews()
        return jsonify([])
    return jsonify(latest_reviews[:5])

@app.route('/get_next_review')
def get_next_review():
    global current_review_index

    if current_review_index >= len(latest_reviews):
        return jsonify({})  # No more reviews to send

    review = latest_reviews[current_review_index]
    current_review_index += 1
    return jsonify(review)


@app.route('/book')
def book():
    book_title = request.args.get('title')
    page = int(request.args.get('page', 1))  # default to page 1
    page_size = int(request.args.get('page_size', DEFAULT_PAGE_SIZE))
    offset = (page - 1) * page_size

    book_description_id = table_title_ids['book_description'][book_title][0]
    book_ratings_ids = table_title_ids['book_ratings'][book_title]
    book_ratings1_ids = table_title_ids['book_ratings1'][book_title]

    book_ratings_ids_str = ",".join([str(id) for id in book_ratings_ids])

    query_book_description = f"SELECT * FROM book_description WHERE id = {book_description_id};"
    query_book_ratings = f"SELECT profilename, score, review FROM book_ratings WHERE id IN ({book_ratings_ids_str}) LIMIT {page_size} OFFSET {offset};"

    result_book_description = execute_query(query_book_description)
    result_book_ratings = execute_query(query_book_ratings)

    # Remove the square brackets and split the string by comma to get a list
    authors_list = result_book_description[0][3][1:-1].split(",")

    # Remove leading and trailing whitespace and single quotes from each author's name
    authors_list = [author.strip().strip("'") for author in authors_list]

    # Convert list of authors into a readable string
    author_str = ", ".join(authors_list)


    book_description = {
        'id': result_book_description[0][0],
        'title': result_book_description[0][1],
        'description': result_book_description[0][2],
        'authors': author_str
    }

    book_reviews = []
    score_count = 0

    total_ratings = 0
    for row in result_book_ratings:
        score = 0
        try:
            score = float(row[1])
            score_count += 1
        except:
            score = 3
        total_ratings += score
        book_reviews.append({
            'profilename': row[0],
            'score': score,
            'review': row[2]
        })

    #result_book_ratings1

    total_reviews = len(book_ratings_ids)
    # Calculate total number of pages
    total_pages = total_reviews // page_size + (1 if total_reviews % page_size else 0)
    average_rating = round(total_ratings / score_count, 1)

    book_description['total_reviews'] = total_reviews
    book_description['average_rating'] = average_rating

    response = {
        'book_description': book_description,
        'book_reviews': book_reviews,
        'total_reviews': total_reviews,
        'average_rating': average_rating,
        'current_page': page,
        'total_pages': total_pages,
        'page_size': page_size
    }

    return render_template('book.html', response=response)


@app.route('/search_autocomplete', methods=['GET'])
def search_autocomplete():
    query = request.args.get('query', '')
    
    # Fetch matching book titles based on the query. This is a pseudo-code.
    matching_books = fetch_matching_books(query, limit=10)
    
    return jsonify(matching_books)

def fetch_matching_books(query, limit=10):
    title_list = table_title_ids['book_description']
    
    # Use difflib to get the closest matches
    matching_books = difflib.get_close_matches(query, title_list, n=limit)
    if query not in matching_books:
        if query in table_title_ids['book_description']:
            matching_books.insert(0, query)

    result = []
    for title in matching_books:
        result.append({'title': title, 'id': table_title_ids['book_description'][title]})
    
    return result


def get_display_reviews(limit=5):
    query = "SELECT * FROM book_ratings FETCH FIRST 10 ROWS ONLY;"
    reviews = execute_query(query)
    return reviews[:limit]


def fetch_initial_reviews():
    global latest_reviews

    query_result = list()
    try:
        with open('initial_results.json') as f:
            query_result = json.load(f)
    except:
        pass

    if query_result is None or len(query_result) == 0:
        random_ids = random.sample(display_ids, 100)
        random_ids_str = ",".join([str(id) for id in random_ids])
        
        qurey = f"SELECT id, title, score, review FROM book_ratings WHERE id IN ({random_ids_str}) LIMIT 50"
        query_result = execute_query(qurey)

    random.shuffle(query_result)

    for row in query_result:
        latest_reviews.append({
            'id': row[0], 
            "title": row[1],
            "score": row[2],
            "review": row[3]
        })

if __name__ == '__main__':
    init_db()
    fetch_initial_reviews()
    app.run(debug=True)
