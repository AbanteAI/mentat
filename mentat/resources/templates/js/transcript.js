/* Helper functions */
function containerWithoutButtons(element) {
    const container = element.closest('.container');
    const clone = container.cloneNode(true);
    clone.querySelectorAll('.button-group').remove();
    const head = document.getElementsByTagName("head")[0].cloneNode(true);
    const html = document.createElement("html");
    const body = document.createElement("body");
    body.appendChild(clone);
    html.appendChild(head);
    html.appendChild(body);
    return html;
}

async function uploadTranscript(page, feedback) {
    const key = Date.now().toString(36) + Math.random().toString(36).substr(2) + '.html';
    let data = {
        "html": page,
        "key": key
    }
    if (feedback) {
        data["feedback"] = feedback
    }
    const endpoint = "https://29g74gpmwk.execute-api.us-east-2.amazonaws.com/default/store-usage-example";
    return fetch(endpoint, {
        method: "POST",
        mode: "no-cors",
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    }).then(response => {
        return `https://abante-shared-usage-examples.s3.us-east-2.amazonaws.com/${key}`;
    })
}

function makeToast(message) {
    const toast = document.createElement("div");
    toast.classList.add("toast");
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.remove();
    }, 3000);
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
    const downloadLinks = document.getElementsByClassName("download-parent");
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
    const feedbackButtons = document.getElementsByClassName("feedback-button");
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
                uploadTranscript(html.outerHTML, feedback).then(s3Url => {
                    makeToast("Thank you for your feedback!");
                    modal.style.display = 'none';
                }).catch(error => {
                    console.error("Error submitting feedback:", error);
                    alert("There was an error submitting your feedback.");
                });
            };
        };
    }

    const shareButtons = document.getElementsByClassName("share-button");
    for (const shareButton of shareButtons) {
        shareButton.onclick = (event) => {
            const current_button = event.currentTarget;
            const html = containerWithoutButtons(current_button);
            uploadTranscript(html.outerHTML, null).then(s3Url => {
                navigator.clipboard.writeText(s3Url).then(() => {
                    makeToast("The link has been copied to your clipboard.");
                }, (err) => {
                    alert("Couldn't access clipboard. The link is: " + s3Url);
                });
            }).catch(error => {
                console.error("Error submitting feedback:", error);
                alert("There was an error uploading the transcript.");
            });
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

