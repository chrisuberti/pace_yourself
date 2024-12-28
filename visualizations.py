import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, to_rgba
import pydeck as pdk
import plotly.express as px

def altitude_colormap(df):
    norm = Normalize(vmin=df["altitude"].min(), vmax=df["altitude"].max())
    cmap = plt.get_cmap("viridis")
    return [to_rgba(cmap(norm(alt))) for alt in df["altitude"]]

# Function to create a pydeck map
def create_map(df):
    df["color"] = altitude_colormap(df)

    # Convert RGBA values to a format that pydeck can understand
    df["color"] = df["color"].apply(lambda x: [int(255 * c) for c in x])

    # Create a pydeck layer
    layer = pdk.Layer(
        'ScatterplotLayer',
        data=df,
        get_position='[lon, lat]',
        get_color='color',
        get_radius=50,
        pickable=True
    )

    # Set the view state
    view_state = pdk.ViewState(
        latitude=df["lat"].mean(),
        longitude=df["lon"].mean(),
        zoom=12,
        pitch=0
    )

    # Create the pydeck Deck object
    return pdk.Deck(layers=[layer], initial_view_state=view_state)

def plot_cumulative_distance_vs_altitude(df):
    df['cumulative_distance'] = df['cumulative_distance'] / 1000  # Convert to kilometers
    fig = px.line(
        df,
        x='cumulative_distance',
        y='altitude',
        #title='Cumulative Distance vs Altitude',
        labels={'cumulative_distance': 'Distance (km)', 'altitude': 'Altitude (m)'},
        template='plotly_dark'  # Use the dark theme
    )
    return fig