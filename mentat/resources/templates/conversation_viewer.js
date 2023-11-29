var at = 0
document.addEventListener('DOMContentLoaded', (event) => {
    transcripts = document.getElementsByClassName("container")
    active = transcripts[at]
    active.classList.add("active")

    document.addEventListener('keydown', function(event) {
        switch (event.key) {
            case 'ArrowLeft':
                if (at == 0) {
                    break;
                }
                active.classList.remove("active")
                active = transcripts[--at]
                active.classList.add("active")
                break;
            case 'ArrowRight':
                if (at == transcripts.length - 1) {
                    break;
                }
                active.classList.remove("active")
                active = transcripts[++at]
                active.classList.add("active")
                break;
        }
    })

    for (element of document.getElementsByClassName('clickable')) {
        element.onclick = (event) => {
            const e = event.currentTarget
            const rightViewer = document.getElementsByClassName("right-viewer")[at]
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

