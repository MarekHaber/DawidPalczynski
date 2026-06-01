import React from "react";



function Form() {
    return(
        <div id="form">
            <form action="">
                <label htmlFor="input-name"> Imie
                <input type="text" placeholder="imie" id="input-imie" />
                </label>
                <input type="text" placeholder="Nazwisko" id="input-nazwisko" />
                <br />
                <input type="email" placeholder="email" id="input-email"/>
                 <br />
                <textarea type="text" placeholder="Wiadomosc" id="input-wiadomosc"/> <br />
                <button>Wyslij</button>
            </form>
        </div>
    );
}

export default Form