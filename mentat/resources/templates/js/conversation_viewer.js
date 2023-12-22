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
})
