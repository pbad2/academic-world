from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()
URI = "bolt://localhost:7687"

AUTH = (
    os.getenv("NEO4J_DB_USER", "neo4j"),
    os.getenv("NEO4J_DB_PASSWORD", ""),
)
database = "academicworld"

driver = GraphDatabase.driver(URI, auth=AUTH, database=database)


def get_all_universities():
    query = "MATCH (i:INSTITUTE) RETURN i.name AS name ORDER BY i.name"
    with driver.session() as session:
        result = session.run(query)
        return [r["name"] for r in result]


def get_top_keywords_by_university(university_name):
    query = """
    MATCH (f:FACULTY)-[:AFFILIATION_WITH]->(i:INSTITUTE {name: $university_name}),
          (f)-[:INTERESTED_IN]->(k:KEYWORD)
    RETURN k.name AS keyword, COUNT(*) AS count
    ORDER BY count DESC
    LIMIT 10
    """
    with driver.session() as session:
        result = session.run(query, university_name=university_name)
        return [{"keyword": r["keyword"], "count": r["count"]} for r in result]


def get_citation_trend_by_keyword(keyword_name):
    query = """
    MATCH (p:PUBLICATION)-[:LABEL_BY]->(k:KEYWORD)
    WHERE toLower(k.name) = toLower($keyword_name)
    RETURN p.year AS year, SUM(p.numCitations) AS totalCitations
    ORDER BY year
    """
    with driver.session() as session:
        result = session.run(query, keyword_name=keyword_name)
        return [
            {"year": r["year"], "totalCitations": r["totalCitations"]} for r in result
        ]
