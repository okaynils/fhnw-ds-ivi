import streamlit as st
import pandas as pd
import pydeck as pdk
import requests

# Load and cache the dataset
@st.cache_data
def load_data():
    data = pd.read_csv('./data/ebd_SE_relSep-2024/ebd_SE_relSep-2024.txt', sep='\t', low_memory=False)
    data['OBSERVATION DATE'] = pd.to_datetime(data['OBSERVATION DATE'])
    return data

data = load_data()

# Filter species
species_list = data['COMMON NAME'].unique()
species = st.sidebar.selectbox('Select Species:', species_list)

# Filter data for the selected species
@st.cache_data
def filter_data(species):
    return data[data['COMMON NAME'] == species]

filtered_data = filter_data(species)

st.title('Birds of Sweden')

# Overview: Show total observations
st.subheader('Total Observations')
st.metric(label="Total Observations", value=len(filtered_data))

# Map with interactive tooltips
st.subheader(f'Map of {species} Observations')

# Define the map layer
layer = pdk.Layer(
    'ScatterplotLayer',
    data=filtered_data,
    get_position='[LONGITUDE, LATITUDE]',
    get_radius=100,
    get_color='[200, 30, 0, 160]',
    pickable=True
)

# Set the viewport location
view_state = pdk.ViewState(
    longitude=filtered_data['LONGITUDE'].mean(),
    latitude=filtered_data['LATITUDE'].mean(),
    zoom=5
)

# Render the deck.gl map
r = pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip={"text": "{LOCALITY}"})
st.pydeck_chart(r)


# Additional Filters in Sidebar
date_range = st.sidebar.date_input(
    "Select Date Range:",
    [filtered_data['OBSERVATION DATE'].min(), filtered_data['OBSERVATION DATE'].max()]
)

# Filter data based on date range
filtered_data = filtered_data[
    (filtered_data['OBSERVATION DATE'] >= pd.to_datetime(date_range[0])) &
    (filtered_data['OBSERVATION DATE'] <= pd.to_datetime(date_range[1]))
]

# Interactive Time Series Chart
st.subheader('Observations Over Time')
time_series = filtered_data.groupby('OBSERVATION DATE').size()
st.line_chart(time_series)

# Details on Demand: Show images when a point is clicked
# Note: Streamlit currently doesn't support click events on pydeck charts directly,
# but we can simulate this with a selection mechanism.

selected_locality = st.selectbox('Select Locality:', filtered_data['LOCALITY'].unique())

locality_data = filtered_data[filtered_data['LOCALITY'] == selected_locality]

st.subheader(f'Images from {selected_locality}')

# Wikimedia API settings
query = species.replace(' ', '_')  # Replace spaces with underscores for the query
url = f'https://en.wikipedia.org/w/api.php?action=query&prop=pageimages|pageprops&format=json&piprop=thumbnail&titles={query}&pithumbsize=300&redirects=1'

response = requests.get(url)

if response.status_code == 200:
    data = response.json()
    pages = data.get('query', {}).get('pages', {})
    for page_id, page_data in pages.items():
        thumbnail = page_data.get('thumbnail', {})
        image_url = thumbnail.get('source')
        if image_url:
            st.image(image_url, caption=species)
        else:
            st.write('No image available for this species.')
else:
    st.write('Failed to retrieve image.')


# Display images for the selected locality
# (Assuming you have a way to retrieve images based on locality)
# For demonstration, we'll reuse the species image
st.image(image_url, caption=f'{species} at {selected_locality}')

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader(f'Map of {species} Observations')
    st.pydeck_chart(r)

with col2:
    st.subheader('Observation Details')
    st.write(filtered_data[['OBSERVATION DATE', 'LOCALITY', 'OBSERVATION COUNT']].head())
