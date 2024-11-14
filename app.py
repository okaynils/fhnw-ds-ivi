import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from functools import lru_cache
import json

# Load GeoJSON file for Sweden's regions
with open('./data/swedish_regions.geojson', 'r') as f:
    sweden_geojson = json.load(f)

# Load and cache the dataset
@lru_cache(maxsize=32)
def load_data():
    data = pd.read_csv('./data/ebd_SE_relSep-2024/ebd_SE_relSep-2024.txt', sep='\t', low_memory=False)
    data['OBSERVATION DATE'] = pd.to_datetime(data['OBSERVATION DATE'])
    # Extract the first word of the "STATE" column for simplified state matching
    data['STATE'] = data['STATE'].apply(lambda x: x.split()[0] if pd.notnull(x) else x)
    # Take away the last character in the STATE column if its "s"
    data['STATE'] = data['STATE'].apply(lambda x: x[:-1] if x.endswith('s') else x)
    return data

data = load_data()
species_list = sorted(data['COMMON NAME'].unique())

# Initialize the Dash app
app = dash.Dash(__name__)
server = app.server

# Custom HTML and Fonts
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        <title>Birds of Sweden</title>
        <link href="https://fonts.googleapis.com/css2?family=Crimson+Pro:wght@400;700&display=swap" rel="stylesheet">
        <link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:ital,wght@0,100..900;1,100..900&display=swap" rel="stylesheet">
    </head>
    <body style="margin: 0px">
        <div id="react-entry-point">
            {%app_entry%}
        </div>
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

# Layout
app.layout = html.Div([
    # Sidebar layout with fixed position
    html.Div([
        html.H1("Birds of Sweden", style={'fontFamily': 'Crimson Pro', 'color': 'white'}),
        dcc.Dropdown(
            id='species-dropdown',
            options=[{'label': sp, 'value': sp} for sp in species_list],
            placeholder="Select a species",
            style={'width': '100%', 'fontFamily': 'Hanken Grotesk', 'color': 'gray'}
        ),
        html.H2(id='species-name', style={'fontFamily': 'Crimson Pro', 'marginTop': '20px', 'color': 'white'}),
        html.H3(id='scientific-name', style={'fontFamily': 'Hanken Grotesk', 'color': 'gray'}),
        html.Img(id='species-image', style={
            'width': '100%', 'height': '150px', 'borderRadius': '10px', 'objectFit': 'cover', 'marginTop': '20px', 'display': 'none'
        }),
        html.Div(id='species-info', style={'color': 'white', 'marginTop': '20px', 'fontFamily': 'Hanken Grotesk'}),
        html.Div(id='state-observations-map', children=[
            dcc.Graph(id='observations-map')
        ], style={'marginTop': '20px'}),
    ], style={
        'width': '25%', 'position': 'fixed', 'backgroundColor': '#2c2f33', 'height': '100vh', 'color': 'white', 
        'padding': '20px', 'boxSizing': 'border-box', 'overflow': 'auto'
    }),

    # Right-side layout
    html.Div([
        dcc.Graph(id='map-graph', style={'height': '100vh'})
    ], style={'width': '75%', 'marginLeft': '25%', 'fontFamily': 'Roboto'})
])

# Callback to update species info and sidebar map
@app.callback(
    [Output('species-name', 'children'),
     Output('scientific-name', 'children'),
     Output('species-image', 'src'),
     Output('species-image', 'style'),
     Output('species-info', 'children'),
     Output('observations-map', 'figure')],
    [Input('species-dropdown', 'value')]
)
def update_species_info(species):
    if species:
        species_name = species
        scientific_name = data[data['COMMON NAME'] == species]['SCIENTIFIC NAME'].iloc[0]
        query = species.replace(' ', '_')
        url = f'https://en.wikipedia.org/w/api.php?action=query&prop=pageimages|pageprops&format=json&piprop=thumbnail&titles={query}&pithumbsize=300&redirects=1'
        response = requests.get(url)
        image_url = next((page['thumbnail']['source'] for page in response.json()['query']['pages'].values() if 'thumbnail' in page), None)
        if not image_url:
            image_url = 'https://via.placeholder.com/100?text=No+Image+Available'
        
        # Extract additional species information
        species_data = data[data['COMMON NAME'] == species].iloc[0]
        species_info = [
            html.P(f"Taxonomic Order: {species_data['TAXONOMIC ORDER']}"),
            html.P(f"Observation Count: {species_data['OBSERVATION COUNT']}"),
            html.P(f"Breeding Category: {species_data['BREEDING CATEGORY']}"),
            html.P(f"State: {species_data['STATE']}"),
            html.P(f"Locality: {species_data['LOCALITY']}")
        ]
        
        # Filter data for observations by state for the selected species
        state_counts = data[data['COMMON NAME'] == species]['STATE'].value_counts().reset_index()
        state_counts.columns = ['STATE', 'observations']
    else:
        species_name = "All Species"
        scientific_name = ""
        image_url = ""
        species_info = ""
        
        # Count all observations by state for all species
        state_counts = data['STATE'].value_counts().reset_index()
        state_counts.columns = ['STATE', 'observations']

    # Create a choropleth map for observations by state
    if state_counts.empty:
        fig = go.Figure()
        fig.update_layout(
            title="No specific observations found",
            xaxis={"visible": False},
            yaxis={"visible": False}
        )
    else:
        fig = px.choropleth(
            state_counts,
            geojson=sweden_geojson,
            locations='STATE',
            color='observations',
            featureidkey="properties.name",
            color_continuous_scale="reds",
            title="Observations by State"
        )
        fig.update_geos(fitbounds="locations", visible=False)
        fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})

    return species_name, scientific_name, image_url, {'display': 'block' if species else 'none'}, species_info, fig

# Callback to update main map with all or filtered data
@app.callback(
    Output('map-graph', 'figure'),
    [Input('species-dropdown', 'value')]
)
def update_map(species):
    if species:
        filtered_data = data[data['COMMON NAME'] == species]
    else:
        filtered_data = data

    if filtered_data.empty or 'LATITUDE' not in filtered_data.columns or 'LONGITUDE' not in filtered_data.columns:
        fig = go.Figure()
        fig.update_layout(mapbox_style="carto-darkmatter", showlegend=False, margin={"r": 0, "t": 0, "l": 0, "b": 0})
        return fig

    fig = px.scatter_mapbox(
        filtered_data,
        lat='LATITUDE',
        lon='LONGITUDE',
        hover_name='COMMON NAME',
        hover_data={'OBSERVATION DATE': True, 'LOCALITY': True},
        zoom=4,
        height=800,
        color_discrete_sequence=['red']
    )
    fig.update_layout(mapbox_style="carto-darkmatter", showlegend=False, margin={"r": 0, "t": 0, "l": 0, "b": 0})
    return fig

# Callback to set species from map click
@app.callback(
    Output('species-dropdown', 'value'),
    [Input('map-graph', 'clickData')]
)
def update_species_from_map_click(clickData):
    if clickData:
        species = clickData['points'][0]['hovertext']
        return species
    return dash.no_update

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)