import React from "react";
import img1 from "./data/DSC08584.jpg";
import img2 from "./data/DSC06229.jpg";
import img3 from "./data/DSC08556.jpg";
import img4 from "./data/DSC09627.jpg";

function Hero() {
    return (
        <div id="hero">
            <div id="Lhero">
                <h1>Uwiecznij najwazniesze chwile.</h1>
                <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit, <br />
                    sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.</p>

                <button className="cta">
                    <a href="/#/Kontakt">
                                <span className="hover-underline-animation"> Skontaktuj się </span>
                    <svg
                        id="arrow-horizontal"
                        xmlns="http://www.w3.org/2000/svg"
                        width="30"
                        height="10"
                        viewBox="0 0 46 16"
                    >
                        <path
                            id="Path_10"
                            data-name="Path 10"
                            d="M8,0,6.545,1.455l5.506,5.506H-30V9.039H12.052L6.545,14.545,8,16l8-8Z"
                            transform="translate(30)"
                        ></path>
                    </svg>
                    </a>
            
                </button>
            </div>
            
            <div id="Rhero">
                <div id="kolumna1">
                    <img src={img1} alt="Fotografia 1" className="zdjk" />
                    <img src={img2} alt="Fotografia 2" className="zdjk" />
                </div>

                <div id="kolumna2">
                    <img src={img3} alt="Fotografia 3" className="zdjk" />
                    <img src={img4} alt="Fotografia 4" className="zdjk" />
                </div>
            </div>
        </div>
    );
}

export default Hero;