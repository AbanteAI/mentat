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
            const container = link.parentElement.parentElement.cloneNode(true);
            const downloadParent = container.querySelector('.download_parent');
            if (downloadParent) {
                downloadParent.remove();
            }
            const head = document.getElementsByTagName("head")[0].cloneNode(true);

            const html = document.createElement("html");
            const body = document.createElement("body");
            body.appendChild(container);
            html.appendChild(head);
            html.appendChild(body);
            
            const blob = new Blob([html.outerHTML], {type: "text/html"});
            const url = URL.createObjectURL(blob);
            link.href = url;

            link.download = `transcript_${container.id}.html`;
        };
    }
})

