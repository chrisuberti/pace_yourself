import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, to_rgba
import pydeck as pdk
import plotly.express as px

def continuous_colormap(df, column = 'altitude'):
    norm = Normalize(vmin=df[column].min(), vmax=df[column].max())
    cmap = plt.get_cmap("viridis")
    return [to_rgba(cmap(norm(alt))) for alt in df[column]]

def categorical_colormap(df, column='segment'):
    unique_values = df[column].unique()
    cmap = plt.get_cmap("tab20", len(unique_values))  # Use a colormap with enough colors
    color_dict = {val: to_rgba(cmap(i)) for i, val in enumerate(unique_values)}
    return [color_dict[val] for val in df[column]]

def create_color_map(df, color = 'altitude'):
    if color == 'gradient':
        df["color"] = continuous_colormap(df, 'gradient')
    elif color == 'altitude':    
        df["color"] = continuous_colormap(df)
    elif color == 'power':
        df["color"] = continuous_colormap(df, 'power')
    elif color == 'speed':
        df["color"] = continuous_colormap(df, 'speed')
    elif color == 'segment':
        df["color"] = categorical_colormap(df, 'segment')

    # Convert RGBA values to a format that pydeck can understand
    df["color"] = df["color"].apply(lambda x: [int(255 * c) for c in x])

    return df

# Function to create a pydeck map
def create_map(df, color = 'altitude'):
    # Create a color map
    df = create_color_map(df, color)

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

def plot_cumulative_distance_vs_altitude(df, color='altitude'):
    """
    Plot cumulative distance vs altitude using a scatter plot to avoid connecting discontinuous segments.

    Args:
        df (pd.DataFrame): The DataFrame containing the data.
        color (str): The column to use for coloring the plot.

    Returns:
        plotly.graph_objects.Figure: The generated plot.
    """
    
    df = create_color_map(df, color)

    if color == 'segment':
        # Use discrete color scale for segments
        fig = px.scatter(
            df,
            x='cumulative_distance',
            y='altitude',
            marker=dict(color='segment'),
            labels={'cumulative_distance': 'Distance (km)', 'altitude': 'Altitude (m)', 'segment': 'Segment'},
            template='plotly_dark',  # Use the dark theme
            title="Cumulative Distance vs Altitude"
        )
    else:
        # Use continuous color scale for other attributes
        fig = px.scatter(
            df,
            x='cumulative_distance',
            y='altitude',
            color=color,
            labels={'cumulative_distance': 'Distance (km)', 'altitude': 'Altitude (m)'},
            template='plotly_dark',  # Use the dark theme
            title="Cumulative Distance vs Altitude"
        )

    return fig