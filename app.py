import dash
from dash import dcc, html, Input, Output, State, ctx, dash_table
import flask
import uuid
from db import mysql_utils, mongodb_utils, neo4j_utils
from db.neo4j_utils import get_citation_trend_by_keyword
import dash_bootstrap_components as dbc
import plotly.graph_objs as go

# Flask server for session management
server = flask.Flask(__name__)
server.secret_key = "your-secret-key"  # For session cookies

# Dash app instance
# suppress_callback_exceptions=True
app = dash.Dash(__name__, server=server, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Discover Research Across Universities"


# Setup session ID
@app.server.before_request
def make_session_permanent():
    flask.session.permanent = True
    if "session_id" not in flask.session:
        flask.session["session_id"] = str(uuid.uuid4())


# Layout
app.layout = html.Div(
    [
        html.H1("Academic World Dashboard", className="my-4"),
        html.Div(
            [
                html.H4("Search by Keyword"),
                dcc.Input(
                    id="keyword-input",
                    type="text",
                    placeholder="Enter keyword",
                    debounce=True,
                ),
                html.Button(
                    "Search", id="search-button", className="btn btn-primary my-2"
                ),
            ]
        ),
        html.Div(id="error-message", style={"color": "red", "fontWeight": "bold"}),
        html.Div(
            [
                html.H4("Top Universities"),
                html.Div(id="university-output"),
                html.H4("Top Professors"),
                html.Div(id="professor-output"),
                html.H4("Top Publications"),
                html.Div(id="publication-output"),
            ],
            style={"marginBottom": "40px"},
        ),
        html.Hr(),
        html.Div(
            [
                html.H4("Add/Remove Favorites (MongoDB)"),
                dcc.Input(id="favorite-input", placeholder="Enter name"),
                dcc.Dropdown(
                    id="favorite-type",
                    options=[
                        {"label": "Professor", "value": "professors"},
                        {"label": "University", "value": "universities"},
                    ],
                    placeholder="Choose type",
                ),
                html.Div(
                    [
                        html.Button("Add to Favorites", id="add-favorite", n_clicks=0),
                        html.Button(
                            "Remove from Favorites", id="remove-favorite", n_clicks=0
                        ),
                    ],
                    style={"marginTop": "10px"},
                ),
            ]
        ),
        html.H4("My Favorites"),
        html.Div(id="favorites-display"),
    ]
)


# Callback for MySQL keyword search
@app.callback(
    Output("university-output", "children"),
    Output("professor-output", "children"),
    Output("publication-output", "children"),
    Input("search-button", "n_clicks"),
    State("keyword-input", "value"),
)
def update_results(n_clicks, keyword):
    try:
        if not keyword:
            raise ValueError("Please enter a keyword.")

        keyword = keyword.strip().lower()
        results = mysql_utils.run_all_keyword_queries_transactional(keyword)

    except ValueError as e:
        return html.Div(str(e), style={"color": "red"}), "", ""

    # BAR CHART: Universities
    uni_fig = {
        "data": [
            go.Bar(
                x=[name for name, _ in results["universities"]],
                y=[score for _, score in results["universities"]],
                marker_color="indigo",
            )
        ],
        "layout": go.Layout(
            margin={"t": 30, "b": 70}, height=250, title="", xaxis={"tickangle": -30}
        ),
    }

    # BAR CHART: Professors
    prof_fig = {
        "data": [
            go.Bar(
                x=[name for name, _ in results["professors"]],
                y=[score for _, score in results["professors"]],
                marker_color="darkgreen",
            )
        ],
        "layout": go.Layout(
            margin={"t": 30, "b": 70}, height=250, title="", xaxis={"tickangle": -30}
        ),
    }

    # TABLE: Publications
    pub_table = dash_table.DataTable(
        columns=[{"name": "Title", "id": "title"}, {"name": "Score", "id": "score"}],
        data=[
            {"title": title, "score": f"{score:.2f}"}
            for title, score in results["publications"]
        ],
        style_table={"height": "250px", "overflowY": "auto"},
        style_cell={"textAlign": "left", "padding": "5px", "whiteSpace": "normal"},
        style_header={"fontWeight": "bold"},
    )

    return dcc.Graph(figure=uni_fig), dcc.Graph(figure=prof_fig), pub_table


@app.callback(
    Output("favorites-display", "children"),
    Input("add-favorite", "n_clicks"),
    Input("remove-favorite", "n_clicks"),
    State("favorite-type", "value"),
    State("favorite-input", "value"),
)
def update_favorites(add_clicks, remove_clicks, category, item):
    session_id = flask.session.get("session_id")

    mongodb_utils.get_or_create_session(session_id)

    if category and item:
        if ctx.triggered_id == "add-favorite":
            mongodb_utils.add_favorite(session_id, category, item)
        elif ctx.triggered_id == "remove-favorite":
            mongodb_utils.remove_favorite(session_id, category, item)

    favs = mongodb_utils.get_favorites(session_id)
    return html.Div(
        [
            html.P("Professors: " + ", ".join(favs.get("professors", []))),
            html.P("Universities: " + ", ".join(favs.get("universities", []))),
            html.P("Topics: " + ", ".join(favs.get("topics", []))),
        ]
    )


@app.callback(
    Output("neo4j-output", "children"),
    Input("search-button", "n_clicks"),
    State("keyword-input", "value"),
)
def update_citation_trend_chart(n_clicks, keyword):
    if not n_clicks or not keyword:
        return html.Div("No keyword provided", style={"color": "gray"})

    try:
        # Get citation trend data from Neo4j
        trend_data = get_citation_trend_by_keyword(keyword.strip().lower())
        if not trend_data:
            return html.Div(
                "No citation data found for that keyword.", style={"color": "gray"}
            )

        # Create a line chart for citation trend
        fig = go.Figure(
            data=[
                go.Scatter(
                    x=[entry["year"] for entry in trend_data],
                    y=[entry["totalCitations"] for entry in trend_data],
                    mode="lines+markers",  # This creates the line with markers on each data point
                    name="Citations",
                )
            ]
        )
        fig.update_layout(xaxis_title="Year", yaxis_title="Total Citations", height=350)

        return dcc.Graph(figure=fig)

    except Exception as e:
        return html.Div(
            f"Error fetching citation data: {str(e)}", style={"color": "red"}
        )


@app.callback(
    Output("university-pie-chart", "figure"),
    Input("university-pie-button", "n_clicks"),
    State("university-pie-dropdown", "value"),
)
def update_university_pie_chart(n_clicks, university_name):
    if not n_clicks or not university_name:
        return {}

    try:
        data = neo4j_utils.get_top_keywords_by_university(university_name)

        if not data:
            return {
                "data": [],
                "layout": {"title": f"No data found for {university_name}"},
            }

        labels = [item["keyword"] for item in data]
        values = [item["count"] for item in data]

        return {
            "data": [
                {
                    "type": "pie",
                    "labels": labels,
                    "values": values,
                    "hole": 0.3,
                    "textinfo": "percent+label",
                    "insidetextorientation": "auto",
                }
            ],
            "layout": {
                "margin": {"t": 10, "b": 10, "l": 10, "r": 10},
                "showlegend": False,
                "height": 500,
                "autosize": True,
                "height": None,
                "width": None,
            },
        }

    except Exception as e:
        return {"data": [], "layout": {"title": f"Error: {str(e)}"}}


@app.callback(
    Output("university-pie-dropdown", "options"), Input("university-pie-dropdown", "id")
)
def load_pie_dropdown_options(_):
    try:
        universities = neo4j_utils.get_all_universities()
        return [{"label": name, "value": name} for name in universities]
    except Exception:
        return []


app.layout = dbc.Container(
    [
        html.H1("Discover Research Across Universities", className="text-center my-4"),
        # Row 1: Pie Chart + Favorites (side-by-side)
        dbc.Row(
            [
                # Pie Chart - Left
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H4(
                                            "Top Research Keywords at a University",
                                            className="mb-3",
                                        ),
                                        dcc.Dropdown(
                                            id="university-pie-dropdown",
                                            placeholder="Select university",
                                            className="mb-2",
                                        ),
                                        dbc.Button(
                                            "Search",
                                            id="university-pie-button",
                                            color="primary",
                                            className="mb-3",
                                        ),
                                        dcc.Graph(
                                            id="university-pie-chart",
                                            style={"height": "320px"},
                                            config={"responsive": True},
                                        ),
                                    ]
                                )
                            ],
                            style={"height": "100%"},
                        )
                    ],
                    md=6,
                ),
                # Favorites - Right
                dbc.Col(
                    [
                        # Favorites Manager
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H4("Favorites Manager"),
                                        dbc.Input(
                                            id="favorite-input",
                                            placeholder="Enter professor or university name",
                                            className="mb-2",
                                        ),
                                        dcc.Dropdown(
                                            id="favorite-type",
                                            options=[
                                                {
                                                    "label": "Professor",
                                                    "value": "professors",
                                                },
                                                {
                                                    "label": "University",
                                                    "value": "universities",
                                                },
                                                {"label": "Topics", "value": "topics"},
                                            ],
                                            placeholder="Choose type",
                                            className="mb-2",
                                        ),
                                        dbc.ButtonGroup(
                                            [
                                                dbc.Button(
                                                    "Add",
                                                    id="add-favorite",
                                                    color="success",
                                                ),
                                                dbc.Button(
                                                    "Remove",
                                                    id="remove-favorite",
                                                    color="danger",
                                                ),
                                            ]
                                        ),
                                    ]
                                )
                            ],
                            className="mb-3",
                        ),
                        # My Favorites
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H4("My Favorites"),
                                        html.Div(
                                            id="favorites-display",
                                            className="bg-light p-2 border rounded",
                                        ),
                                    ]
                                )
                            ]
                        ),
                    ],
                    md=6,
                    style={
                        "display": "flex",
                        "flexDirection": "column",
                        "height": "100%",
                    },
                ),
            ]
        ),
        html.Br(),
        # Row 2: Keyword search + Top Results
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H4("Search by Keyword"),
                                        dcc.Input(
                                            id="keyword-input",
                                            type="text",
                                            placeholder="Enter Keyword",
                                            className="form-control mb-2",
                                        ),
                                        dbc.Button(
                                            "Search",
                                            id="search-button",
                                            color="primary",
                                        ),
                                    ]
                                )
                            ],
                            className="mb-3",
                        )
                    ]
                )
            ]
        ),
        # Row of 3 result cards
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H5("Top Universities"),
                                        html.Div(id="university-output"),
                                    ]
                                )
                            ],
                            style={"height": "100%"},
                        )
                    ],
                    md=4,
                ),
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H5("Top Professors"),
                                        html.Div(id="professor-output"),
                                    ]
                                )
                            ],
                            style={"height": "100%"},
                        )
                    ],
                    md=4,
                ),
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H5("Top Publications"),
                                        html.Div(id="publication-output"),
                                    ]
                                )
                            ],
                            style={"height": "100%"},
                        )
                    ],
                    md=4,
                ),
            ]
        ),
        html.Br(),
        # Row 3: Citation Trend
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H4("Citation Trends", className="mb-3"),
                                        html.Div(
                                            id="neo4j-output",
                                            className="bg-light p-2 border rounded",
                                        ),
                                    ]
                                )
                            ]
                        )
                    ]
                )
            ]
        ),
    ],
    fluid=True,
)


if __name__ == "__main__":
    app.run(debug=True)
