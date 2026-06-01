import React from "react";


function Footer() {

    const rok = new Date().getFullYear();

    return(
        <div id="footer">
            <p> © {rok}, Dawid Pałczyńsi.  </p>
        </div>
    );
}

export default Footer