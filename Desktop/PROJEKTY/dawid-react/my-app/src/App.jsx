import { useState } from 'react'
import './App.css'
import Nav from './assets/nav'
import Hero from './assets/hero'
import Section from './assets/section'
import Recent from './assets/recent'
import Footer from './assets/footer'
import Kontakt from './Kontakt'
import Button from './assets/cta'
import { HashRouter, Routes, Route } from 'react-router-dom'

function App() {
  return (
    <HashRouter>
      <Nav />
      
      <Routes>
        <Route path="/" element={
          <>
            <Hero />
            <Section />
            <Recent />
          </>
        } />

        <Route path="/kontakt" element={<Kontakt />} />
      </Routes>
      <Footer />
    </HashRouter>
  )
}

export default App