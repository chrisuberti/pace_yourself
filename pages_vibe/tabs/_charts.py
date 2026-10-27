"""
Shared chart builders for the Race Lab tabs.

All Plotly figure construction lives here so tab modules stay focused on
flow control and state. Functions are pure (input -> figure); they do not
touch session state and do not call st.plotly_chart.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ── Course tab charts ──────────────────────────────────────────────────────

def build_gps_map(cdf: pd.DataFrame) -> go.Figure:
    """Plotly map of the raw course GPS trace.

    Colors points by gradient if available, else plain blue line.
    """
    fig = go.Figure()

    if 'gradient' in cdf.columns:
        fig.add_trace(go.Scattermap(
            lat=cdf['lat'], lon=cdf['lon'],
            mode='markers+lines',
            marker=dict(
                size=4,
                color=cdf['gradient'] * 100,
                colorscale='RdYlGn_r',
                cmin=-10, cmax=10,
                colorbar=dict(title='Grade %', thickness=12, len=0.6),
            ),
            line=dict(width=2, color='gray'),
            hovertemplate=(
                'Lat: %{lat:.4f}<br>Lon: %{lon:.4f}<br>'
                'Grade: %{marker.color:.1f}%<extra></extra>'
            ),
        ))
    else:
        fig.add_trace(go.Scattermap(
            lat=cdf['lat'], lon=cdf['lon'],
            mode='lines',
            line=dict(width=3, color='#3498db'),
        ))

    center_lat = cdf['lat'].mean()
    center_lon = cdf['lon'].mean()
    lat_range = cdf['lat'].max() - cdf['lat'].min()
    lon_range = cdf['lon'].max() - cdf['lon'].min()
    max_range = max(lat_range, lon_range)
    zoom = 15 if max_range < 0.01 else 13 if max_range < 0.05 else 12 if max_range < 0.1 else 10

    fig.update_layout(
        map=dict(
            style='open-street-map',
            center=dict(lat=center_lat, lon=center_lon),
            zoom=zoom,
        ),
        height=380,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )
    return fig


def build_virtual_course_map(cdf: pd.DataFrame) -> go.Figure:
    """Draw virtual route geometry without placing it on a real-world map."""
    fig = go.Figure(go.Scatter(
        x=cdf['lon'],
        y=cdf['lat'],
        mode='lines',
        line=dict(width=4, color='#ff4b4b'),
        hoverinfo='skip',
    ))
    fig.update_layout(
        height=380,
        template='plotly_dark',
        xaxis=dict(visible=False, scaleanchor='y', scaleratio=1),
        yaxis=dict(visible=False),
        margin=dict(l=10, r=10, t=35, b=10),
        title=dict(text='Virtual course map', x=0.5, xanchor='center'),
        showlegend=False,
    )
    return fig


def build_elevation_profile(cdf: pd.DataFrame) -> go.Figure:
    """Elevation profile chart for the loaded course.

    Falls back to plain area fill if no gradient column.
    """
    dist_km = cdf['cumulative_distance'] / 1000
    fig = go.Figure()

    if 'gradient' in cdf.columns:
        fig.add_trace(go.Scatter(
            x=dist_km, y=cdf['altitude'],
            fill='tozeroy', fillcolor='rgba(149,165,166,0.15)',
            line=dict(color='rgba(149,165,166,0.4)', width=0.5),
            showlegend=False, hoverinfo='skip',
        ))
        fig.add_trace(go.Scatter(
            x=dist_km, y=cdf['altitude'],
            mode='markers',
            marker=dict(
                size=3,
                color=cdf['gradient'] * 100,
                colorscale='RdYlGn_r',
                cmin=-10, cmax=10,
                showscale=False,
            ),
            hovertemplate='%{y:.0f}m · %{marker.color:.1f}%<extra></extra>',
            showlegend=False,
        ))
    else:
        fig.add_trace(go.Scatter(
            x=dist_km, y=cdf['altitude'],
            fill='tozeroy', fillcolor='rgba(149,165,166,0.3)',
            line=dict(color='gray', width=1),
            showlegend=False,
            hovertemplate='%{y:.0f}m<extra></extra>',
        ))

    fig.update_layout(
        height=380, template='plotly_dark',
        xaxis_title='Distance (km)', yaxis_title='Elevation (m)',
        margin=dict(l=50, r=20, t=10, b=40),
        showlegend=False,
    )
    return fig


# ── Rider tab charts ────────────────────────────────────────────────────────

def build_power_duration_curve(cp: int, w_prime: int,
                               best_efforts: dict | None = None,
                               athlete_label: str | None = None,
                               provenance: str | None = None) -> go.Figure:
    """Power-duration curve with optional cached athlete best efforts."""
    durations = np.array([5, 10, 15, 30, 60, 120, 180, 300,
                          600, 900, 1200, 1800, 3600])
    powers = cp + w_prime / durations

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=durations, y=powers,
        mode='lines+markers',
        line=dict(color='#e67e22', width=2),
        name="CP + W' model",
        hovertemplate='%{x}s → %{y:.0f}W<extra></extra>',
    ))
    efforts = best_efforts or {}
    if efforts:
        effort_durations = sorted(efforts)
        fig.add_trace(go.Scatter(
            x=effort_durations,
            y=[efforts[duration] for duration in effort_durations],
            mode='markers',
            marker=dict(color='#ff4b4b', size=10, symbol='diamond'),
            name='Strava best efforts',
            hovertemplate='%{x}s → %{y:.0f}W<extra>Strava PB</extra>',
        ))
    fig.add_hline(y=cp, line=dict(color='red', dash='dot'),
                  annotation_text=f"CP = {cp}W")
    fig.update_xaxes(
        type='log', title='Duration',
        tickvals=[5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600],
        ticktext=['5s', '10s', '30s', '1m', '2m', '5m', '10m',
                  '20m', '30m', '1hr'],
    )
    fig.update_yaxes(title='Power (W)', range=[0, 1500])
    title = None
    if athlete_label:
        subtitle = provenance or 'Cached Strava best efforts'
        title = f"<b>{athlete_label}</b><br><sup>{subtitle}</sup>"
    fig.update_layout(
        height=380 if title else 350, template='plotly_dark',
        margin=dict(l=50, r=30, t=95 if title else 20, b=40),
        showlegend=bool(efforts),
        legend=dict(orientation='h', y=1.03, x=1, xanchor='right'),
        title=(dict(
            text=title, x=0, xanchor='left', y=0.92, yanchor='top')
            if title else None),
    )
    return fig


# ── Optimization tab chart ──────────────────────────────────────────────────

def build_results_chart(results: dict, rider_config: dict, course_obj) -> go.Figure:
    """Multi-panel Plotly comparison chart for optimization results.

    Panel 1: Power (primary y) + Elevation (secondary y) with terrain colors
    Panel 2: Time delta (Compare Both only)
    Panel 3: W' balance
    """
    has_c = 'constant' in results
    has_v = 'variable' in results
    cp = rider_config['critical_power']

    ref = results.get('variable', results.get('constant'))
    det = ref['detailed']
    dist_km = det['cumulative_distance'] / 1000
    altitude = det['altitude']

    work_annotations = []
    if has_c:
        c_det = results['constant']['detailed']
        const_work_kj = (c_det['power'] * c_det['time']).sum() / 1000
        work_annotations.append(f"Const: {const_work_kj:.1f} kJ")
    if has_v:
        v_det = results['variable']['detailed']
        var_work_kj = (v_det['power'] * v_det['time']).sum() / 1000
        work_annotations.append(f"Var: {var_work_kj:.1f} kJ")

    n_rows = 3 if (has_c and has_v) else 2
    row_heights = [0.5, 0.25, 0.25] if n_rows == 3 else [0.6, 0.4]
    subtitles = (["Power & Elevation", "Time Delta", "W' Balance"]
                 if n_rows == 3 else ["Power & Elevation", "W' Balance"])
    specs = [[{"secondary_y": True}]] + [[{"secondary_y": False}]] * (n_rows - 1)

    fig = make_subplots(
        rows=n_rows, cols=1, shared_xaxes=True,
        vertical_spacing=0.04, row_heights=row_heights,
        subplot_titles=subtitles, specs=specs,
    )

    _add_elevation_traces(fig, course_obj, det, dist_km, altitude)

    if has_c:
        fig.add_trace(go.Scatter(
            x=dist_km, y=results['constant']['detailed']['power'],
            line=dict(color='#3498db', width=1.8, dash='dash', shape='hv'),
            name="Constant Power", opacity=0.9,
            hovertemplate='%{y:.0f}W<extra>Constant</extra>',
        ), row=1, col=1, secondary_y=False)

    if has_v:
        fig.add_trace(go.Scatter(
            x=dist_km, y=results['variable']['detailed']['power'],
            line=dict(color='#e67e22', width=1.8, shape='hv'),
            name="Variable Pacing", opacity=0.9,
            hovertemplate='%{y:.0f}W<extra>Variable</extra>',
        ), row=1, col=1, secondary_y=False)

    fig.add_hline(y=cp, line=dict(color='red', width=1, dash='dot'),
                  annotation_text=f"CP = {cp}W",
                  annotation_font=dict(color='red', size=10),
                  row=1, col=1, secondary_y=False)

    work_text = "Total Work — " + "  |  ".join(work_annotations)
    fig.add_annotation(
        text=work_text, xref='x domain', yref='y domain',
        x=0.98, y=0.02, showarrow=False,
        font=dict(size=10, color='white'),
        bgcolor='rgba(50,50,50,0.7)',
        bordercolor='gray', borderwidth=1, borderpad=4,
        row=1, col=1,
    )

    current_row = 2

    if has_c and has_v:
        _add_time_delta_panel(fig, results, dist_km, current_row)
        current_row += 1

    w_max_kj = rider_config['w_prime'] / 1000
    _add_w_prime_panel(fig, results, dist_km, w_max_kj, current_row)

    total_height = 750 if n_rows == 3 else 550
    fig.update_layout(
        height=total_height, template='plotly_dark',
        margin=dict(l=60, r=60, t=40, b=40),
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='center', x=0.5, font=dict(size=11)),
        hovermode='x unified',
    )
    power_range = _power_axis_range(results, cp)
    fig.update_yaxes(title_text="Power (W)", row=1, col=1,
                     secondary_y=False, range=power_range)
    fig.update_yaxes(title_text="Elevation (m)", row=1, col=1,
                     secondary_y=True, showgrid=False,
                     title_font=dict(color='gray'),
                     tickfont=dict(color='gray'))
    if has_c and has_v:
        fig.update_yaxes(title_text="Time Δ (s)", row=2, col=1)
    fig.update_yaxes(title_text="W' (kJ)", row=current_row, col=1,
                     range=[-0.5, w_max_kj * 1.1])
    fig.update_xaxes(title_text="Distance (km)", row=current_row, col=1)

    return fig


# ── Optimization sub-builders ───────────────────────────────────────────────

def _power_axis_range(results: dict, critical_power: float) -> list[float]:
    """Return a padded range containing every plotted power value and CP."""
    plotted_power = [float(critical_power)]
    for strategy in ('constant', 'variable'):
        detailed = results.get(strategy, {}).get('detailed')
        if detailed is None or 'power' not in detailed:
            continue
        values = np.asarray(detailed['power'], dtype=float)
        plotted_power.extend(values[np.isfinite(values)].tolist())

    minimum = min(plotted_power)
    maximum = max(plotted_power)
    span = maximum - minimum
    padding = max(
        15.0,
        span * 0.08,
        float(critical_power) * 0.05,
    )
    if span == 0:
        padding = max(padding, float(critical_power) * 0.15)
    return [max(0.0, minimum - padding), maximum + padding]


def _add_elevation_traces(fig, course_obj, det, dist_km, altitude):
    """Add terrain-colored or plain elevation fill to panel 1."""
    terrain_values = set()
    if 'segment_terrain' in course_obj.df.columns:
        terrain_values = set(course_obj.df['segment_terrain'].dropna().unique())
    is_terrain = (terrain_values <= {'uphill', 'flat', 'downhill'}
                  and len(terrain_values) > 0)

    if is_terrain and 'segment_index' in det.columns:
        terrain_fill = {
            'uphill': 'rgba(46,204,113,0.25)',
            'flat': 'rgba(149,165,166,0.25)',
            'downhill': 'rgba(231,76,60,0.25)',
        }
        terrain_line = {
            'uphill': 'rgb(46,204,113)',
            'flat': 'rgb(149,165,166)',
            'downhill': 'rgb(231,76,60)',
        }
        terrain_labels = {'uphill': 'Uphill', 'flat': 'Flat',
                          'downhill': 'Downhill'}
        seg_terrain_map = (course_obj.df
                           .groupby('segment')['segment_terrain']
                           .first().to_dict())
        seg_idx = det['segment_index']
        shown = set()
        prev = seg_terrain_map.get(
            int(seg_idx.iloc[0]) if pd.notna(seg_idx.iloc[0]) else 0, 'flat')
        run_start = 0

        def _flush(start, end, terrain):
            sl = slice(start, end)
            show_leg = terrain not in shown
            if show_leg:
                shown.add(terrain)
            fig.add_trace(go.Scatter(
                x=dist_km.iloc[sl], y=altitude.iloc[sl],
                fill='tozeroy',
                fillcolor=terrain_fill.get(terrain, terrain_fill['flat']),
                line=dict(color=terrain_line.get(terrain,
                                                 terrain_line['flat']),
                          width=0.8),
                name=terrain_labels.get(terrain, terrain),
                legendgroup=f'terrain_{terrain}',
                showlegend=show_leg,
                hovertemplate=('%{y:.0f}m<extra>'
                               + terrain_labels.get(terrain, '')
                               + '</extra>'),
                opacity=0.6,
            ), row=1, col=1, secondary_y=True)

        for i in range(1, len(seg_idx)):
            cur = seg_terrain_map.get(
                int(seg_idx.iloc[i]) if pd.notna(seg_idx.iloc[i]) else 0,
                'flat')
            if cur != prev:
                _flush(run_start, i + 1, prev)
                run_start = i
                prev = cur
        _flush(run_start, len(seg_idx), prev)
    else:
        fig.add_trace(go.Scatter(
            x=dist_km, y=altitude,
            fill='tozeroy', fillcolor='rgba(149,165,166,0.2)',
            line=dict(color='rgba(149,165,166,0.5)', width=0.8),
            name='Elevation', showlegend=False,
            hovertemplate='%{y:.0f}m<extra></extra>', opacity=0.6,
        ), row=1, col=1, secondary_y=True)


def _add_time_delta_panel(fig, results, dist_km, row):
    c_det = results['constant']['detailed']
    v_det = results['variable']['detailed']
    min_len = min(len(c_det), len(v_det))
    time_delta = (c_det['cumulative_time'].values[:min_len]
                  - v_det['cumulative_time'].values[:min_len])
    td_dist = dist_km.iloc[:min_len]

    td_pos = np.where(time_delta >= 0, time_delta, 0)
    td_neg = np.where(time_delta < 0, time_delta, 0)

    fig.add_trace(go.Scatter(
        x=td_dist, y=td_pos,
        fill='tozeroy', fillcolor='rgba(230,126,34,0.3)',
        line=dict(color='rgba(0,0,0,0)', width=0),
        name='Variable ahead', hoverinfo='skip',
    ), row=row, col=1)
    fig.add_trace(go.Scatter(
        x=td_dist, y=td_neg,
        fill='tozeroy', fillcolor='rgba(52,152,219,0.3)',
        line=dict(color='rgba(0,0,0,0)', width=0),
        name='Constant ahead', hoverinfo='skip',
    ), row=row, col=1)
    fig.add_trace(go.Scatter(
        x=td_dist, y=time_delta,
        line=dict(color='#2c3e50', width=1.2),
        name='Time Δ', showlegend=False,
        hovertemplate='%{y:+.1f}s<extra></extra>',
    ), row=row, col=1)
    fig.add_hline(y=0, line=dict(color='gray', width=1), row=row, col=1)

    final_d = time_delta[-1]
    fig.add_annotation(
        x=float(td_dist.iloc[-1]), y=float(final_d),
        text=f"{final_d:+.1f}s",
        showarrow=True, arrowhead=2,
        font=dict(size=11,
                  color='#e67e22' if final_d >= 0 else '#3498db',
                  weight='bold'),
        row=row, col=1,
    )


def _add_w_prime_panel(fig, results, dist_km, w_max_kj, row):
    if 'constant' in results:
        c_det = results['constant']['detailed']
        fig.add_trace(go.Scatter(
            x=dist_km, y=c_det['w_remaining'] / 1000,
            line=dict(color='#3498db', width=1.5, dash='dash'),
            fill='tozeroy', fillcolor='rgba(52,152,219,0.1)',
            name="W' Constant",
            hovertemplate="%{y:.1f} kJ<extra>Constant</extra>",
        ), row=row, col=1)

    if 'variable' in results:
        v_det = results['variable']['detailed']
        fig.add_trace(go.Scatter(
            x=dist_km, y=v_det['w_remaining'] / 1000,
            line=dict(color='#e67e22', width=1.5),
            fill='tozeroy', fillcolor='rgba(230,126,34,0.1)',
            name="W' Variable",
            hovertemplate="%{y:.1f} kJ<extra>Variable</extra>",
        ), row=row, col=1)

    fig.add_hline(y=0, line=dict(color='red', width=1.5), row=row, col=1)
    fig.add_hline(y=w_max_kj, line=dict(color='gray', width=1, dash='dot'),
                  opacity=0.3, row=row, col=1)
