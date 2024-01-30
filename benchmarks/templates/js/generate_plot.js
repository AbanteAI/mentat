var traceMain = {
    x: [
        {% for summary in summary_list if summary.metadata["branch"] == 'main' %}
            "{{summary.metadata["date"]}}",
        {% endfor %}
    ],
    y: [
        {% for summary in summary_list if summary.metadata["branch"] == 'main' %}
            {{summary["summary"]["cost"][0]}},
        {% endfor %}
    ],
    mode: 'lines+markers',
    type: 'scatter',
    name: 'Main Branch',
    text: [
        {% for summary in summary_list if summary.metadata["branch"] == 'main' %}
            "{{summary.metadata["file"]}}",
        {% endfor %}
    ],
    line: {
        color: 'black'
    },
    marker: {
        color: 'black'
    }
};

var traceOther = {
    x: [
        {% for summary in summary_list if summary.metadata["branch"] != 'main' %}
            "{{summary.metadata["date"]}}",
        {% endfor %}
    ],
    y: [
        {% for summary in summary_list if summary.metadata["branch"] != 'main' %}
            {{summary.summary["cost"][0]}},
        {% endfor %}
    ],
    mode: 'markers',
    type: 'scatter',
    name: 'Other Branches',
    text: [
        {% for summary in summary_list if summary.metadata["branch"] != 'main' %}
            "{{summary.metadata["file"]}}",
        {% endfor %}
    ],
    marker: {
        color: 'red'
    }
};

var data = [traceMain, traceOther];

ys = {
    {% for property in summary_list[-1].summary.keys() %}
        {% if summary_list[-1].summary[property][1] > 0 %}
            "{{ property }}": {
                y: [[
                    {% for summary in summary_list %}
                        {% if summary.metadata["branch"] == 'main' %}
                            {{summary.summary[property][0]}},
                        {% endif %}
                    {% endfor %}
                ], [
                    {% for summary in summary_list %}
                        {% if summary.metadata["branch"] != 'main' %}
                            {{summary.summary[property][0]}},
                        {% endif %}
                    {% endfor %}
                ]]
            },
        {% endif %}
    {% endfor %}
};
var layout = {
    title: 'Benchmarks',
    showlegend: true,
    updatemenus: [{
        y: 0.8,
        yanchor: 'top',
        buttons: Object.keys(ys).map(function(metric) {
            return {
                method: 'update',
                args: [{
                    y: [ys[metric].y[0], ys[metric].y[1]],
                }],
                label: metric
            };
        }),
        direction: 'down',
        showactive: true,
    }]
};
var currentMetric = 'cost';

var config = {responsive: true}

document.addEventListener('DOMContentLoaded', (event) => {
    var plot = document.getElementById('plot');

// send a message to the contentWindow
plot.postMessage(
    {
        task: 'listen',
        events: ['zoom','click','hover']
    }, 'https://plot.ly');

window.addEventListener('message', function(e) {
    var message = e.data;
    alert(message.type);
    console.log(message); // prints object for zoom, click, or hover event
});
});

