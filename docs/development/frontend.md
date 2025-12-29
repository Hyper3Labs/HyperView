# Frontend Development

Learn how to develop and contribute to the HyperView frontend.

## Overview

The HyperView frontend is built with:

- **Next.js 16**: React framework with App Router
- **React 18**: UI components
- **TypeScript**: Type safety
- **Tailwind CSS**: Styling
- **regl-scatterplot**: WebGL scatter plots
- **Zustand**: State management

## Development Setup

### Install Dependencies

```bash
cd frontend
npm install
```

### Development Mode

For the best development experience, run the backend and frontend separately:

#### Terminal 1: Backend Server

```bash
# From project root
source .venv/bin/activate
python scripts/demo.py --samples 200 --no-browser
```

This starts the API server at **http://127.0.0.1:5151**

#### Terminal 2: Frontend Dev Server

```bash
# From project root
cd frontend
npm run dev
```

This starts the dev server at **http://localhost:3000** with:
- ✅ Hot reloading
- ✅ Fast Refresh
- ✅ Instant feedback on changes
- ✅ API proxy to backend

### API Proxying

The dev server automatically proxies API requests:

```typescript
// In next.config.ts
async rewrites() {
  return [
    {
      source: '/api/:path*',
      destination: 'http://127.0.0.1:5151/api/:path*'
    }
  ]
}
```

This means:
- Frontend calls `/api/dataset`
- Request goes to `http://127.0.0.1:5151/api/dataset`
- No CORS issues!

## Project Structure

```
frontend/
├── app/
│   ├── page.tsx              # Main application page
│   ├── layout.tsx            # Root layout
│   └── globals.css           # Global styles
├── components/
│   ├── ImageGrid.tsx         # Left panel: image browser
│   ├── ScatterPlot.tsx       # Right panel: visualization
│   ├── Controls.tsx          # View toggles and filters
│   ├── Header.tsx            # Top navigation
│   └── LoadingState.tsx      # Loading indicators
├── lib/
│   ├── api.ts                # API client functions
│   ├── store.ts              # Zustand state management
│   └── types.ts              # TypeScript types
├── public/
│   └── favicon.ico
├── next.config.ts            # Next.js configuration
├── tailwind.config.ts        # Tailwind configuration
├── tsconfig.json             # TypeScript configuration
└── package.json
```

## Key Components

### ImageGrid Component

Displays paginated image thumbnails:

```typescript
// components/ImageGrid.tsx
export function ImageGrid() {
  const { samples, selectedIds, toggleSelection } = useStore()
  
  return (
    <div className="grid grid-cols-4 gap-2">
      {samples.map(sample => (
        <ImageCard
          key={sample.id}
          sample={sample}
          selected={selectedIds.has(sample.id)}
          onClick={() => toggleSelection(sample.id)}
        />
      ))}
    </div>
  )
}
```

### ScatterPlot Component

WebGL-based scatter plot visualization:

```typescript
// components/ScatterPlot.tsx
export function ScatterPlot({ mode }: { mode: 'euclidean' | 'hyperbolic' }) {
  const plotRef = useRef<ScatterplotGL>()
  const { embeddings, selectedIds } = useStore()
  
  useEffect(() => {
    if (!plotRef.current) return
    
    const data = mode === 'euclidean'
      ? embeddings.euclidean
      : embeddings.hyperbolic
    
    plotRef.current.draw(data)
  }, [mode, embeddings])
  
  return <canvas ref={canvasRef} />
}
```

### State Management

Zustand store for global state:

```typescript
// lib/store.ts
interface AppState {
  // Data
  dataset: Dataset | null
  samples: Sample[]
  embeddings: Embeddings | null
  
  // UI State
  selectedIds: Set<string>
  viewMode: 'euclidean' | 'hyperbolic'
  currentPage: number
  
  // Actions
  loadDataset: () => Promise<void>
  loadSamples: (page: number) => Promise<void>
  loadEmbeddings: () => Promise<void>
  toggleSelection: (id: string) => void
  setViewMode: (mode: 'euclidean' | 'hyperbolic') => void
}

export const useStore = create<AppState>((set, get) => ({
  // Initial state
  dataset: null,
  samples: [],
  embeddings: null,
  selectedIds: new Set(),
  viewMode: 'euclidean',
  currentPage: 1,
  
  // Actions
  loadDataset: async () => {
    const data = await fetchDataset()
    set({ dataset: data })
  },
  // ...
}))
```

## API Integration

### API Client

Centralized API calls:

```typescript
// lib/api.ts
const API_BASE = process.env.NODE_ENV === 'production'
  ? '/api'
  : '/api' // Proxied in dev

export async function fetchDataset(): Promise<Dataset> {
  const response = await fetch(`${API_BASE}/dataset`)
  return response.json()
}

export async function fetchSamples(page: number): Promise<Sample[]> {
  const response = await fetch(`${API_BASE}/samples?page=${page}`)
  return response.json()
}

export async function fetchEmbeddings(): Promise<Embeddings> {
  const response = await fetch(`${API_BASE}/embeddings`)
  return response.json()
}
```

### Error Handling

```typescript
// lib/api.ts
export async function fetchWithError<T>(url: string): Promise<T> {
  try {
    const response = await fetch(url)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }
    return response.json()
  } catch (error) {
    console.error('API Error:', error)
    throw error
  }
}
```

## Styling

### Tailwind CSS

We use Tailwind for utility-first styling:

```typescript
<div className="flex h-screen">
  <div className="w-1/2 bg-gray-50 p-4">
    {/* Left panel */}
  </div>
  <div className="w-1/2 bg-white p-4">
    {/* Right panel */}
  </div>
</div>
```

### Custom Styles

For component-specific styles:

```typescript
// components/ImageCard.tsx
import styles from './ImageCard.module.css'

export function ImageCard({ sample, selected }: Props) {
  return (
    <div className={`${styles.card} ${selected ? styles.selected : ''}`}>
      {/* ... */}
    </div>
  )
}
```

## Building for Production

### Development Build

```bash
npm run dev
```

### Production Build

```bash
# Build and export to static files
npm run build

# Preview production build
npm run start
```

### Export to Python Package

```bash
# From project root
./scripts/export_frontend.sh
```

This:
1. Builds the frontend
2. Exports to static HTML/CSS/JS
3. Copies to `src/hyperview/server/static/`
4. Makes it available to `hv.launch()`

## Testing

### Manual Testing

1. Start backend: `python scripts/demo.py --no-browser`
2. Start frontend: `npm run dev`
3. Open http://localhost:3000
4. Test features:
   - ✅ Image grid loads
   - ✅ Pagination works
   - ✅ Scatter plot renders
   - ✅ Toggle between views
   - ✅ Selection syncs
   - ✅ Responsive layout

### Browser DevTools

Use React DevTools:

```bash
# Install React DevTools extension
# Then inspect components in browser
```

## Common Tasks

### Add a New Component

```typescript
// components/MyComponent.tsx
interface MyComponentProps {
  data: string[]
}

export function MyComponent({ data }: MyComponentProps) {
  return (
    <div className="p-4">
      {data.map(item => <div key={item}>{item}</div>)}
    </div>
  )
}
```

### Add to State

```typescript
// lib/store.ts
interface AppState {
  // Add new state
  myNewData: string[]
  
  // Add new action
  setMyNewData: (data: string[]) => void
}

export const useStore = create<AppState>((set) => ({
  myNewData: [],
  
  setMyNewData: (data) => set({ myNewData: data }),
}))
```

### Add New API Endpoint

```typescript
// lib/api.ts
export async function fetchMyData(): Promise<MyData> {
  const response = await fetch(`${API_BASE}/my-endpoint`)
  return response.json()
}
```

## Performance Tips

### 1. Memoization

```typescript
import { useMemo } from 'react'

function MyComponent({ data }: Props) {
  const processedData = useMemo(
    () => expensiveComputation(data),
    [data]
  )
  
  return <div>{processedData}</div>
}
```

### 2. Lazy Loading

```typescript
import { lazy, Suspense } from 'react'

const HeavyComponent = lazy(() => import('./HeavyComponent'))

function App() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <HeavyComponent />
    </Suspense>
  )
}
```

### 3. Virtual Scrolling

For large lists, consider react-window:

```bash
npm install react-window
```

## Debugging

### Console Logging

```typescript
console.log('Dataset loaded:', dataset)
console.error('Failed to load:', error)
```

### React DevTools

- Inspect component props and state
- Track component re-renders
- Profile performance

### Network Tab

- Check API requests
- Verify response data
- Monitor loading times

## Next Steps

- [Contributing Guide](contributing.md) - How to contribute
- [Architecture](../concepts/architecture.md) - System overview
- [API Reference](../getting-started/api.md) - Backend API
