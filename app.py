import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import pandas as pd
import json
from functools import lru_cache
import requests

import folium
from folium.plugins import MarkerCluster

app = dash.Dash(__name__)
server = app.server

# -----------------------------------------------------------------------------
# 1) Load data & GeoJSON
# -----------------------------------------------------------------------------
@lru_cache(maxsize=32)
def load_data():
    data = pd.read_csv('./data/ebd_SE_relSep-2024/ebd_SE_relSep-2024.txt', sep='\t', low_memory=False)[:20000]
    data['OBSERVATION DATE'] = pd.to_datetime(data['OBSERVATION DATE'])
    data = data.dropna(subset=['STATE', 'LATITUDE', 'LONGITUDE', 'COMMON NAME'])
    data['STATE'] = data['STATE'].apply(lambda x: x.split()[0] if pd.notnull(x) else x)
    data['STATE'] = data['STATE'].apply(lambda x: x[:-1] if x.endswith('s') else x)
    return data

data = load_data()
species_list = sorted(data['COMMON NAME'].unique())

with open('./data/swedish_regions.geojson', 'r') as f:
    sweden_geojson = json.load(f)

# -----------------------------------------------------------------------------
# 2) Dash layout
# -----------------------------------------------------------------------------
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

app.layout = html.Div([
    # Sidebar
    html.Div([
        html.H1("Birds of Sweden", style={'fontFamily': 'Crimson Pro', 'color': 'white'}),
        dcc.Dropdown(
            id='species-dropdown',
            options=[{'label': sp, 'value': sp} for sp in species_list],
            placeholder="Select a species",
            value=None,
            style={'width': '100%', 'fontFamily': 'Hanken Grotesk', 'color': 'gray'}
        ),
        html.H2(id='species-name', style={'fontFamily': 'Crimson Pro', 'marginTop': '20px', 'color': 'white'}),
        html.H3(id='scientific-name', style={'fontFamily': 'Hanken Grotesk', 'color': 'gray'}),
        html.Img(
            id='species-image',
            style={
                'width': '100%', 'height': '150px', 'borderRadius': '10px',
                'objectFit': 'cover', 'marginTop': '20px', 'display': 'none'
            }
        ),
        html.Div(id='species-info', style={'color': 'white', 'marginTop': '20px', 'fontFamily': 'Hanken Grotesk'}),
        html.Div(
            id='state-observations-map',
            children=[
                html.Iframe(
                    id='folium-map',
                    style={'width': '100%', 'height': '60vh', 'border': 'none'}
                )
            ],
            style={'flexGrow': '1', 'height': 'auto', 'display': 'flex', 'flexDirection': 'column'}
        ),
    ], style={
        'width': '25%',
        'position': 'fixed',
        'backgroundColor': '#2c2f33',
        'height': '100vh',
        'color': 'white',
        'padding': '20px',
        'boxSizing': 'border-box',
        'display': 'flex',
        'flexDirection': 'column',
        'overflow': 'auto'
    }),

    # Right side
    html.Div([
        html.Iframe(
            id='cluster-map',
            style={'width': '100%', 'height': '100vh', 'border': 'none'}
        )
    ], style={'width': '75%', 'marginLeft': '25%', 'fontFamily': 'Roboto'})
])

# -----------------------------------------------------------------------------
# 3) Callbacks
# -----------------------------------------------------------------------------

# 3A) Left panel: species info + choropleth
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
        species_data = data[data['COMMON NAME'] == species]
        scientific_name = species_data['SCIENTIFIC NAME'].iloc[0]

        # Attempt to fetch an image
        query = species.replace(' ', '_')
        url = (f'https://en.wikipedia.org/w/api.php?action=query&prop=pageimages|pageprops'
               f'&format=json&piprop=thumbnail&titles={query}&pithumbsize=300&redirects=1')
        response = requests.get(url)
        image_url = next(
            (
                pg.get('thumbnail', {}).get('source')
                for pg in response.json()['query']['pages'].values()
                if 'thumbnail' in pg
            ),
            'https://via.placeholder.com/100?text=No+Image+Available'
        )

        # Some basic info
        species_data_sample = species_data.iloc[0]
        species_info = [
            html.P(f"Taxonomic Order: {species_data_sample['TAXONOMIC ORDER']}", style={'margin': '2px 0'}),
            html.P(f"Observation Count: {species_data_sample['OBSERVATION COUNT']}", style={'margin': '2px 0'}),
            html.P(f"Breeding Category: {species_data_sample['BREEDING CATEGORY']}", style={'margin': '2px 0'}),
            html.P(f"State: {species_data_sample['STATE']}", style={'margin': '2px 0'}),
            html.P(f"Locality: {species_data_sample['LOCALITY']}", style={'margin': '2px 0'})
        ]

        species_name = species
        img_display_style = {'display': 'block'}
        # State-level counts for the choropleth
        state_counts = species_data['STATE'].value_counts().reset_index()
        state_counts.columns = ['STATE', 'observations']
    else:
        # "All Species"
        species_name = "All Species"
        scientific_name = ""
        image_url = ""
        species_info = []
        img_display_style = {'display': 'none'}
        state_counts = data['STATE'].value_counts().reset_index()
        state_counts.columns = ['STATE', 'observations']

    # Build the dark choropleth
    m = folium.Map(
        location=[63.0, 16.0],
        zoom_start=5,
        tiles="CartoDB dark_matter"   # Dark tiles
    )
    folium.Choropleth(
        geo_data=sweden_geojson,
        name="choropleth",
        data=state_counts,
        columns=['STATE', 'observations'],
        key_on="feature.properties.name",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name="Observations"
    ).add_to(m)

    # Convert to HTML
    map_html = m.get_root().render()
    map_html = map_html.replace(
        "<head>",
        "<head><style>html, body {width: 100%; height: 100%; margin: 0; padding: 0;}</style>"
    )

    return (
        species_name,
        scientific_name,
        image_url,
        img_display_style,
        species_info,
        map_html
    )

# 3B) Right panel: MarkerCluster map with wider and scroll-free popups
@app.callback(
    Output('cluster-map', 'srcDoc'),
    [Input('species-dropdown', 'value')]
)
def update_cluster_map(species):
    if species:
        filtered_data = data[data['COMMON NAME'] == species]
    else:
        filtered_data = data

    # Initialize the map
    m = folium.Map(
        location=[63.0, 16.0],
        zoom_start=5,
        tiles="CartoDB dark_matter"  # Dark tiles
    )
    marker_cluster = MarkerCluster().add_to(m)

    # Prepare a list to hold unique IDs for each marker
    marker_ids = []

    # Add markers with popups and invisible interaction markers
    for idx, row in filtered_data.iterrows():
        lat, lon = row['LATITUDE'], row['LONGITUDE']
        popup_html = f"""
            <div class="custom-popup">
                <h4>{row['COMMON NAME']}</h4>
                <p><b>Observation Date:</b> {row['OBSERVATION DATE'].strftime('%Y-%m-%d')}</p>
                <p><b>Locality:</b> {row['LOCALITY']}</p>
                <p><b>State:</b> {row['STATE']}</p>
            </div>
        """
        popup = folium.Popup(folium.IFrame(popup_html, width=350, height=140), max_width=350)

        # Create a unique ID for each marker
        marker_id = f"marker_{idx}"
        marker_ids.append(marker_id)

        # Visible CircleMarker
        folium.CircleMarker(
            location=[lat, lon],
            radius=6,  # Visible marker radius
            color="red",
            fill=True,
            fill_color="red",
            fill_opacity=0.7,
            popup=popup,  # Assign the popup to the visible marker
            tooltip=folium.Tooltip(marker_id, permanent=False, opacity=0)
        ).add_to(marker_cluster)

        # Invisible larger CircleMarker for interaction
        folium.CircleMarker(
            location=[lat, lon],
            radius=20,  # Larger radius for easier hover detection
            color=None,  # No border
            fill=True,
            fill_color="transparent",
            fill_opacity=0,  # Fully transparent
            tooltip=folium.Tooltip(marker_id, permanent=False, opacity=0)
        ).add_to(marker_cluster)

    # Render the map to HTML
    map_html = m.get_root().render()

    # ------------- [ 1) Inject JS for popups on hover ] ---------------
    hover_script = f"""
    <script>
    document.addEventListener('DOMContentLoaded', function() {{
        // Iterate through all unique marker IDs
        const markerIds = {marker_ids};

        markerIds.forEach(function(id) {{
            // Find the invisible marker by its tooltip (which contains the unique ID)
            var invisibleMarker = null;
            map.eachLayer(function(layer) {{
                if (layer instanceof L.CircleMarker) {{
                    var tooltip = layer.getTooltip();
                    if (tooltip && tooltip.getContent() === id) {{
                        invisibleMarker = layer;
                    }}
                }}
            }});

            if (invisibleMarker) {{
                // Find the corresponding visible marker
                var visibleMarker = null;
                map.eachLayer(function(layer) {{
                    if (layer instanceof L.CircleMarker && layer.getRadius() === 6) {{
                        var tooltip = layer.getTooltip();
                        if (tooltip && tooltip.getContent() === id) {{
                            visibleMarker = layer;
                        }}
                    }}
                }});

                if (visibleMarker) {{
                    invisibleMarker.on('mouseover', function(e) {{
                        visibleMarker.openPopup();
                    }});
                    invisibleMarker.on('mouseout', function(e) {{
                        visibleMarker.closePopup();
                    }});
                }}
            }}
        }});
    }});
    </script>
    """

    # ------------- [ 2) Inject CSS for tooltip font size ] ---------------
    custom_css = """
    <style>
    .custom-popup h4 {
        font-size: 18px !important;
    }
    .custom-popup p {
        font-size: 14px !important;
    }
    </style>
    """

    # Inject the custom CSS and JS before the closing </body> tag
    map_html = map_html.replace("</head>", f"</head>\n{custom_css}")
    map_html = map_html.replace("</body>", f"{hover_script}\n</body>")

    return map_html

# -----------------------------------------------------------------------------
# 4) Run server
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    app.run_server(debug=True)
