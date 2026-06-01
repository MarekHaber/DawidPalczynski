import React, { useRef, useLayoutEffect, useState } from "react";
import { motion, useScroll, useTransform } from "framer-motion";

import img1 from "./data/DSC00615.jpg";
import img2 from "./data/Dsc00062.jpg";
import img3 from "./data/Dsc01347.jpg";
import img4 from "./data/DSC04797.jpg";
import img5 from "./data/DSC01860.jpg";
import img6 from "./data/DSC07973.jpg";
import img7 from "./data/DSC02125.jpg";
import img8 from "./data/DSC01512.jpg";
import img9 from "./data/DSC05645.jpg";

function Recent() {
  const containerRef = useRef(null);
  const trackRef = useRef(null);
  const [maxScroll, setMaxScroll] = useState(0);

  const images = [
    img1, img2, img3, img4, img5,
    img6, img7, img8, img9
  ];

  const calculateWidth = () => {
    if (!trackRef.current) return;

    const totalWidth = trackRef.current.scrollWidth;
    const viewportWidth = window.innerWidth;

    // +20px bezpieczeństwa żeby nic nie ucięło
    setMaxScroll(totalWidth - viewportWidth + 20);
  };

  useLayoutEffect(() => {
    calculateWidth();

    window.addEventListener("resize", calculateWidth);

    return () => {
      window.removeEventListener("resize", calculateWidth);
    };
  }, []);

  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start start", "end end"]
  });

  const x = useTransform(scrollYProgress, [0, 1], [0, -maxScroll]);

  return (
    <div ref={containerRef} style={{ height: "400vh" }}>

      <div
        style={{
          position: "sticky",
          top: 0,
          height: "100vh",
          overflow: "hidden",
        }}
      >
        <h1
          style={{
            textAlign: "center",
            paddingTop: 40,
            fontSize: 40
          }}
        >
          Moje ostatnie realizacje
        </h1>

        <motion.div
          ref={trackRef}
          style={{
            x,
            display: "flex",
            gap: 15,
            padding: "80px 50px"
          }}
        >
          {images.map((img, index) => (
            <div key={index} style={{ flexShrink: 0 }}>
              <img
                src={img}
                alt=""
                onLoad={calculateWidth} // przelicza po załadowaniu
                style={{
                  width: 480,
                  height: 550,
                  objectFit: "cover",
                  borderRadius: 20
                }}
              />
            </div>
          ))}
        </motion.div>
      </div>
    </div>
  );
}

export default Recent;
