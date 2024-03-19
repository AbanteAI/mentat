import plotly.graph_objs as go
from plotly.offline import plot

# An array of filters to trace property
filters = [
    (
        (
            lambda x: x.metadata["branch"] == "main"
            and x.metadata["type"] == "exercism"
            and x.metadata["language"] == "python"
        ),
        {
            "mode": "lines+markers",
            "name": "main python exercism",
            "line": {"color": "green"},
            "marker": {"color": "green"},
        },
    ),
    (
        (
            lambda x: x.metadata["branch"] != "main"
            and x.metadata["type"] == "exercism"
            and x.metadata["language"] == "python"
        ),
        {
            "mode": "markers",
            "name": "python exercism experiments",
            "marker": {"color": "green"},
        },
    ),
    (
        (
            lambda x: x.metadata["branch"] == "main"
            and x.metadata["type"] == "exercism"
            and x.metadata["language"] == "javascript"
        ),
        {
            "mode": "lines+markers",
            "name": "main javascript exercism",
            "line": {"color": "red"},
            "marker": {"color": "red"},
        },
    ),
    (
        (
            lambda x: x.metadata["branch"] != "main"
            and x.metadata["type"] == "exercism"
            and x.metadata["language"] == "javascript"
        ),
        {
            "mode": "markers",
            "name": "javascript exercism experiments",
            "marker": {"color": "red"},
        },
    ),
    (
        (lambda x: x.metadata["branch"] == "main" and x.metadata["type"] != "exercism"),
        {
            "mode": "lines+markers",
            "name": "main real world",
            "line": {"color": "black"},
            "marker": {"color": "black"},
        },
    ),
    (
        (lambda x: x.metadata["branch"] != "main" and x.metadata["type"] != "exercism"),
        {
            "mode": "markers",
            "name": "real world experiments",
            "marker": {"color": "black"},
        },
    ),
]


def generate_plot_html(summary_list):
    summary_list = sorted(summary_list, key=lambda x: x.metadata["date"])

    data = []
    for f, props in filters:
        data.append(
            go.Scatter(
                x=[summary.metadata["date"] for summary in summary_list if f(summary)],
                y=[summary.summary["passed"][0] for summary in summary_list if f(summary)],
                text=[summary.metadata["file"] for summary in summary_list if f(summary)],
                **props,
            )
        )

    # Generate buttons for each metric available in the summaries
    metrics = list(summary_list[0].summary.keys())
    buttons = []
    for metric in metrics:
        ys = []
        for f, props in filters:
            ys.append([summary.summary[metric][0] for summary in summary_list if f(summary)])
        buttons.append(dict(args=[{"y": ys}], label=metric, method="update"))

    # Add the buttons to the layout
    updatemenus = list(
        [
            dict(
                buttons=buttons,
                direction="down",
                pad={"r": 10, "t": 10},
                showactive=True,
                x=1,
                xanchor="right",
                y=0.9,
                active=metrics.index("passed"),
                yanchor="middle",
            ),
        ]
    )

    layout = go.Layout(title="Benchmarks", showlegend=True, updatemenus=updatemenus)

    fig = go.Figure(data=data, layout=layout)
    return plot(fig, output_type="div", include_plotlyjs=True)
