from django.test import TestCase
from selectors import get_author_with_books
from django.db.models import Prefetch
from models import Author, Book, Publisher, Profile

def get_author_with_books(author_id):
    """
    Selector fetching Author, directly joining immediate relations 
    (Author profile) and prefetching nested relations (Books and their Publishers).
    """
    return Author.objects.select_related("profile").prefetch_related(
        Prefetch(
            "books", 
            queryset=Book.objects.select_related("publisher")
        )
    ).get(id=author_id)

def setup_author_database():
    # Create author
    author = Author.objects.create(name="John Doe")
    # Create related profile
    Profile.objects.create(author=author, bio="...") 
    # Create books with publisher
    Book.objects.create(author=author, title="Book 1", publisher=Publisher.objects.create(name="Pub 1"))
    Book.objects.create(author=author, title="Book 2", publisher=Publisher.objects.create(name="Pub 2"))

class AuthorQueryOptimizationTests(TestCase):
    def setUp(self):
        self.author = setup_author_database()

    def test_author_endpoint_has_no_n_plus_one(self):
        # Establish the absolute maximum allowed queries for this operation
        # Any spike beyond this baseline indicates an N+1 query loop
        with self.assertNumQueries(2): 
            author = get_author_with_books(author_id=1)
            # Accessing related fields will trigger zero extra queries now
            books = author.books.all() 
