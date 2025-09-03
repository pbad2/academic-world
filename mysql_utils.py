import os
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

load_dotenv()


def get_mysql_connection():
    return mysql.connector.connect(
        host=os.getenv("SQL_DB_HOST", "localhost"),
        user=os.getenv("SQL_DB_USER", "root"),
        password=os.getenv("SQL_DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "academicworld"),
    )


def create_indexes():
    conn = get_mysql_connection()
    cursor = conn.cursor()

    index_queries = [
        ## NON PRIMARY KEY
        # keyword
        "CREATE INDEX IF NOT EXISTS idx_keyword_name ON keyword(name);",
        ### ALL BELOW SHOULD EXIST BC THEY ARE PRIMARY KEY.
        # faculty_keyword
        "CREATE INDEX IF NOT EXISTS idx_faculty_keyword_keywordid ON faculty_keyword(keyword_id);",
        "CREATE INDEX IF NOT EXISTS idx_faculty_keyword_facultyid ON faculty_keyword(faculty_id);",
        # faculty -> university
        "CREATE INDEX IF NOT EXISTS idx_faculty_universityid ON faculty(university_id);",
        # publication_keyword
        "CREATE INDEX IF NOT EXISTS idx_publication_keyword_keywordid ON Publication_Keyword(keyword_id);",
        "CREATE INDEX IF NOT EXISTS idx_publication_keyword_pubid ON Publication_Keyword(publication_id);",
    ]

    for query in index_queries:
        try:
            cursor.execute(query)
        except:  # noqa: E722
            pass

    conn.commit()
    cursor.close()
    conn.close()


# Call index creation at python module load time
create_indexes()


def keyword_exists(keyword: str) -> bool:
    if keyword is not None:
        keyword = keyword.strip().lower()
    query = "SELECT 1 FROM keyword WHERE name = %s LIMIT 1;"
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(query, (keyword,))
    exists = cursor.fetchone() is not None
    cursor.close()
    conn.close()
    return exists


def run_all_keyword_queries_transactional(keyword: str):
    if keyword is not None:
        keyword = keyword.strip().lower()

    if not keyword_exists(keyword):
        raise ValueError(f"Keyword '{keyword}' does not exist in the database.")

    conn = get_mysql_connection()
    try:
        # Start a read-only transaction with consistent snapshot
        conn.start_transaction(readonly=True, isolation_level='REPEATABLE READ')
        cursor = conn.cursor(prepared=True)


        # Query 1: Top Universities
        query_universities = """
            SELECT u.name AS university_name, SUM(fk.score) AS total_score
            FROM faculty_keyword fk
            JOIN faculty f ON fk.faculty_id = f.id
            JOIN university u ON f.university_id = u.id
            JOIN keyword k ON fk.keyword_id = k.id
            WHERE k.name = %s
            GROUP BY u.id
            ORDER BY total_score DESC
            LIMIT 5;
        """
        cursor.execute(query_universities, (keyword,))
        universities = cursor.fetchall()

        # Query 2: Top Professors
        query_professors = """
            SELECT f.name AS professor_name, SUM(fk.score) AS total_score
            FROM faculty_keyword fk
            JOIN faculty f ON fk.faculty_id = f.id
            JOIN keyword k ON fk.keyword_id = k.id
            WHERE k.name = %s
            GROUP BY f.id
            ORDER BY total_score DESC
            LIMIT 5;
        """
        cursor.execute(query_professors, (keyword,))
        professors = cursor.fetchall()

        # Query 3: Top Publications
        query_publications = """
            SELECT p.title AS publication_title, pk.score AS keyword_score
            FROM Publication_Keyword pk
            JOIN publication p ON pk.publication_id = p.ID
            JOIN keyword k ON pk.keyword_id = k.id
            WHERE k.name = %s
            ORDER BY pk.score DESC
            LIMIT 5;
        """
        cursor.execute(query_publications, (keyword,))
        publications = cursor.fetchall()

        conn.commit()
        return {
            "universities": universities,
            "professors": professors,
            "publications": publications,
        }

    except Error as e:
        conn.rollback()
        raise RuntimeError(f"Transaction failed: {e}")

    finally:
        cursor.close()
        conn.close()
