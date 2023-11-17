var at = 0
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
