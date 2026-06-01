import React from "react";

function OfferItem({ number, title, description, id }) {
  return (
    <div className="cap" id={id}>
      <span className="Duzy">{number}</span>
      <span className="napis">{title}</span>
      <p className="text">{description}</p>
    </div>
  );
}

const offers = [
  {
    id: "jeden", // To ID poprawnie trafi do pierwszego elementu
    number: "01",
    title: "Śluby i wesela",
    description: "Zapamiętaj jeden z najważniejszych dni"
  },
  {
    number: "02",
    title: "Eventy",
    description: "Imprezy firmowe i te mniejsze np. urodziny"
  },
  {
    number: "03",
    title: "Sesje zdjęciowe",
    description: "Potrzebujesz profesjonalnych zdjęć, a może chcesz mieć co wrzucić na Instagrama?"
  },
  {
    number: "04",
    title: "I wiele więcej",
    description: "Skontaktuj się ze mną przez formularz"
  },
];

function Section() {
  return (
    <div id="section2">
      <h1 id="h1">Co fotografuje?</h1>
      <div id="nagrywam">
        {offers.map((offer) => (
          <OfferItem
            key={offer.number}
            id={offer.id} 
            number={offer.number}
            title={offer.title}
            description={offer.description}
          />
        ))}
      </div>
    </div>
  );
}

export default Section;