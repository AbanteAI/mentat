/* Helper functions */
function containerWithoutButtons(element) {
    const container = element.closest('.container');
    const clone = container.cloneNode(true);
    const buttonsToRemove = clone.querySelectorAll('.download_parent, .feedback_button');
    buttonsToRemove.forEach(button => button.remove());
    const head = document.getElementsByTagName("head")[0].cloneNode(true);

    const html = document.createElement("html");
    const body = document.createElement("body");
    body.appendChild(clone);
    html.appendChild(head);
    html.appendChild(body);

    return html;
}

document.addEventListener('DOMContentLoaded', (event) => {

    for (element of document.getElementsByClassName('clickable')) {
        element.onclick = (event) => {
            const e = event.currentTarget
            const rightViewer = e.parentElement.nextElementSibling
            const old_messages = rightViewer.getElementsByClassName("message")
            while (old_messages[0]) {
                old_messages[0].remove()
            }
            for(selected of document.getElementsByClassName("selected")) {
                selected.classList.remove("selected")
            }
            e.classList.add("selected")

            for (new_message of e.children) {
                if (new_message.classList.contains("viewpoint-message")) {
                    const clone = new_message.cloneNode(true)
                    clone.classList.remove("hidden")
                    rightViewer.appendChild(clone)
                }
            }
        }
    }
    const downloadLinks = document.getElementsByClassName("download_parent");
    for (downloadLink of downloadLinks) {
        downloadLink.onclick = (event) => {
            const link = event.currentTarget;
            const html = containerWithoutButtons(link);
            const blob = new Blob([html.outerHTML], {type: "text/html"});
            const url = URL.createObjectURL(blob);
            link.href = url;

            link.download = `transcript.html`;
        };
    }
    const feedbackButtons = document.getElementsByClassName("feedback_button");
    for (const feedbackButton of feedbackButtons) {
        feedbackButton.onclick = (event) => {
            const modal = document.getElementById('feedback-modal');
            modal.style.display = 'block';
            const closeButton = modal.querySelector('.close-button');
            const form = document.getElementById('feedback-form');
            const current_button = event.currentTarget;

            closeButton.onclick = () => {
                modal.style.display = 'none';
            };

            form.onsubmit = (event) => {
                event.preventDefault();
                const feedback = document.getElementById('feedback-input').value;
                const html = containerWithoutButtons(current_button);
                const key = Date.now().toString(36) + Math.random().toString(36).substr(2) + '.html';
                data = {
                    "html": html.outerHTML,
                    "feedback": feedback,
                    "key": key
                };
                const endpoint = "https://29g74gpmwk.execute-api.us-east-2.amazonaws.com/default/store-usage-example";
                fetch(endpoint, {
                    method: "POST",
                    mode: "no-cors",
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                }).then(response => {
                    alert("Thank you for your feedback!");
                    const s3Url = `https://abante-shared-usage-examples.s3.us-east-2.amazonaws.com/${key}`;
                    navigator.clipboard.writeText(s3Url).then(() => {
                        alert("Thank you for your feedback. The link has been copied to your clipboard.");
                        document.getElementById('feedback-message').textContent = "Thank you for your feedback. The link has been copied to your clipboard.";
                    }, (err) => {
                        console.error('Could not copy text: ', err);
                        document.getElementById('feedback-message').textContent = "Thank you for your feedback. The link is: " + s3Url;
                    });
                }).catch(error => {
                    console.error("Error submitting feedback:", error);
                    alert("There was an error submitting your feedback.");
                });
            };
        };
    }

    document.querySelector('.modal-content').onclick = (event) => {
        event.stopPropagation();
    };
    window.onclick = (event) => {
        const modal = document.getElementById('feedback-modal');
        if (event.target == modal) {
            modal.style.display = 'none';
            document.getElementById('feedback-message').textContent = '';
        }
    };
})

