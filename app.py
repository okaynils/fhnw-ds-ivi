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
    data = pd.read_csv('./data/ebd_SE_relSep-2024/ebd_SE_relSep-2024.txt', sep='\t', low_memory=False)[:20000]
    data['OBSERVATION DATE'] = pd.to_datetime(data['OBSERVATION DATE'])
    # Drop rows with missing essential columns
    data = data.dropna(subset=['STATE', 'LATITUDE', 'LONGITUDE', 'COMMON NAME'])
    # Clean up the 'STATE' column
    data['STATE'] = data['STATE'].apply(lambda x: x.split()[0] if pd.notnull(x) else x)
    data['STATE'] = data['STATE'].apply(lambda x: x[:-1] if x.endswith('s') else x)
    return data

data = load_data()
species_list = sorted(data['COMMON NAME'].unique())

# Initialize the Dash app
app = dash.Dash(__name__)
server = app.server

# Custom HTML and Fonts (same as before)
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
            value=None,  # Ensure no species is selected initially
            style={'width': '100%', 'fontFamily': 'Hanken Grotesk', 'color': 'gray'}
        ),
        html.H2(id='species-name', style={'fontFamily': 'Crimson Pro', 'marginTop': '20px', 'color': 'white'}),
        html.H3(id='scientific-name', style={'fontFamily': 'Hanken Grotesk', 'color': 'gray'}),
        html.Img(id='species-image', style={
            'width': '100%', 'height': '150px', 'borderRadius': '10px', 'objectFit': 'cover', 'marginTop': '20px', 'display': 'none'
        }),
        html.Div(id='species-info', style={'color': 'white', 'marginTop': '20px', 'fontFamily': 'Hanken Grotesk'}),
        html.Div(id='state-observations-map', children=[
            html.Iframe(
                id='folium-map',
                style={
                    'width': '100%',
                    'height': '60vh',  # Increase height to 60% of the viewport height
                    'border': 'none'
                }
            )
        ], style={
            'flexGrow': '1',  # Make the map container expand to fill available space
            'height': 'auto',
            'display': 'flex',
            'flexDirection': 'column'
        }),
    ], style={
        'width': '25%', 
        'position': 'fixed', 
        'backgroundColor': '#2c2f33', 
        'height': '100vh',  # Ensure the sidebar takes up full viewport height
        'color': 'white', 
        'padding': '20px', 
        'boxSizing': 'border-box', 
        'display': 'flex',
        'flexDirection': 'column',  # Stack sidebar elements vertically
        'overflow': 'auto'  # Allow scrolling if necessary
    }),

    # Right-side layout
    html.Div([
        dcc.Graph(id='map-graph', style={'height': '100vh'})
    ], style={'width': '75%', 'marginLeft': '25%', 'fontFamily': 'Roboto'})
])




import folium
from dash.exceptions import PreventUpdate

@app.callback(
    [
        Output('species-name', 'children'),
        Output('scientific-name', 'children'),
        Output('species-image', 'src'),
        Output('species-image', 'style'),
        Output('species-info', 'children'),
        Output('folium-map', 'srcDoc')
    ],
    [Input('species-dropdown', 'value')]
)
def update_species_info(species):
    if species:
        species_name = species
        species_data = data[data['COMMON NAME'] == species]
        scientific_name = species_data['SCIENTIFIC NAME'].iloc[0]
        query = species.replace(' ', '_')
        url = f'https://en.wikipedia.org/w/api.php?action=query&prop=pageimages|pageprops&format=json&piprop=thumbnail&titles={query}&pithumbsize=300&redirects=1'
        response = requests.get(url)
        image_url = next(
            (page.get('thumbnail', {}).get('source') for page in response.json()['query']['pages'].values() if 'thumbnail' in page),
            'https://via.placeholder.com/100?text=No+Image+Available'
        )

        # Extract additional species information
        species_info = []
        species_data_sample = species_data.iloc[0]
        species_info.append(html.P(f"Taxonomic Order: {species_data_sample['TAXONOMIC ORDER']}"))
        species_info.append(html.P(f"Observation Count: {species_data_sample['OBSERVATION COUNT']}"))
        species_info.append(html.P(f"Breeding Category: {species_data_sample['BREEDING CATEGORY']}"))
        species_info.append(html.P(f"State: {species_data_sample['STATE']}"))
        species_info.append(html.P(f"Locality: {species_data_sample['LOCALITY']}"))

        # Filter data for observations by state for the selected species
        state_counts = species_data['STATE'].value_counts().reset_index()
        state_counts.columns = ['STATE', 'observations']
    else:
        species_name = "All Species"
        scientific_name = ""
        image_url = ""
        species_info = []

        # Count all observations by state for all species
        state_counts = data['STATE'].value_counts().reset_index()
        state_counts.columns = ['STATE', 'observations']

    # Generate Folium map
    m = folium.Map(location=[63.0, 16.0], zoom_start=5)
    folium.Choropleth(
        geo_data=sweden_geojson,
        name="choropleth",
        data=state_counts,
        columns=['STATE', 'observations'],
        key_on="feature.properties.name",  # Ensure this matches your GeoJSON properties
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name="Observations"
    ).add_to(m)

    # Save the map to an HTML string and inject custom CSS for full height and width
    map_html = m.get_root().render()
    map_html = map_html.replace(
        "<head>",
        "<head><style>html, body {width: 100%; height: 100%; margin: 0; padding: 0;}</style>"
    )

    return (
        species_name,
        scientific_name,
        image_url,
        {'display': 'block' if species else 'none'},
        species_info,
        map_html
    )


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

    # Drop rows with missing 'LATITUDE' or 'LONGITUDE'
    filtered_data = filtered_data.dropna(subset=['LATITUDE', 'LONGITUDE'])

    if filtered_data.empty:
        fig = go.Figure()
        fig.update_layout(
            mapbox_style="carto-darkmatter",
            showlegend=False,
            margin={"r": 0, "t": 0, "l": 0, "b": 0}
        )
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
    fig.update_layout(
        mapbox_style="carto-darkmatter",
        showlegend=False,
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        hovermode='closest'
    )
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