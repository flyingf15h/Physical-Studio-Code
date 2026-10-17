// Screen 1 · Describe the project. Anyone can open the ready-made guides. To design their own, a
// visitor connects their own AI (Claude Code, Claude Desktop, Cursor) to our MCP server with a
// personal key; it designs from the parts library and the guide shows up under Your projects.
// The example prompts (Senna's Claude) and the parts library (Kelly's Claude) fill the prompt.
import { useState } from 'react'
import { ConnectAI } from '../components/ConnectAI'
import { ExamplePrompts } from '../components/ExamplePrompts'
import { PartsLibrary } from '../components/PartsLibrary'
import { ProgressHeader } from '../components/ProgressHeader'
import { ReadyMadeGuides, YourProjects } from '../components/ProjectsList'
import './DescribePage.css'

export function DescribePage() {
  const [prompt, setPrompt] = useState('')
  const [keyVersion, setKeyVersion] = useState(0)

  return (
    <div className="page">
      <ProgressHeader active={1} />
      <main className="page-body describe-page">
        <section className="describe-main">
          <h1>What do you want to build?</h1>
          <p className="describe-lede">
            Open a ready-made guide, or connect your own AI: it designs your project out of real parts with real
            dimensions, looks up what each part really looks like, and gives you a 3D step-by-step guide.
          </p>
          <h2 className="describe-sub">Try a ready-made guide</h2>
          <ReadyMadeGuides />
          <h2 className="describe-sub">Design your own with your AI</h2>
          <ConnectAI prompt={prompt} setPrompt={setPrompt} onKey={() => setKeyVersion((v) => v + 1)} />
          <h2 className="describe-sub">Ideas to start from</h2>
          <ExamplePrompts onPick={setPrompt} />
          <h2 className="describe-sub">Your projects</h2>
          <YourProjects keyVersion={keyVersion} />
        </section>
        <PartsLibrary onPick={(part) => setPrompt(prompt.trim() ? `${prompt.trim()} ${part.name}` : part.name)} />
      </main>
    </div>
  )
}
