import { createRoot } from "react-dom/client";

import Chat from "./views/Chat";

const domNode = document.getElementById("root");
if (domNode === null) {
  throw Error("'root' element not found");
}
const root = createRoot(domNode);
root.render(<Chat />);
