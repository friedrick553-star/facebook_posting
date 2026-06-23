import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import {
  LayoutDashboard, Filter, Car, Bell, Activity, FileText, Settings,
  Play, Mail, KeyRound,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"

function Step({ n, children }: { n: number; children: ReactNode }) {
  return (
    <li className="flex gap-3 text-sm">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-bold">
        {n}
      </span>
      <span className="text-muted-foreground pt-0.5">{children}</span>
    </li>
  )
}

function SectionLink({ to, icon: Icon, label }: { to: string; icon: React.ComponentType<{ className?: string }>; label: string }) {
  return (
    <Link to={to} className="inline-flex items-center gap-1.5 text-primary hover:underline font-medium">
      <Icon className="h-3.5 w-3.5" />
      {label}
    </Link>
  )
}

export default function HelpPage() {
  return (
    <div className="space-y-6 animate-fade-in max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold">Help</h1>
        <p className="text-muted-foreground text-sm mt-1">How to use the vehicle monitoring dashboard</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Quick Start</CardTitle>
          <CardDescription>Get monitoring running in four steps</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="space-y-3 list-none p-0 m-0">
            <Step n={1}>Go to <SectionLink to="/filters" icon={Filter} label="Filters" /> — set your search criteria, then click <strong>Save</strong>.</Step>
            <Step n={2}>Go to <SectionLink to="/settings" icon={Settings} label="Settings" /> — add your alert email and send a test if needed.</Step>
            <Step n={3}>Click <strong>Start</strong> in the header to enable automatic 24/7 monitoring.</Step>
            <Step n={4}>Check <SectionLink to="/listings" icon={Car} label="Listings" /> and <SectionLink to="/notifications" icon={Bell} label="Notifications" /> for results.</Step>
          </ol>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
          <CardDescription>Two-step search: Facebook fetch, then match & alert</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-muted-foreground">
          <p>
            <strong className="text-foreground">Step 1 — Marketplace Search:</strong> location (city + radius), min/max price, and brand — same as Facebook Vehicles sidebar. Opens{" "}
            <code className="text-xs bg-muted px-1 py-0.5 rounded">/marketplace/category/vehicles</code> style results for your area.
          </p>
          <p>
            <strong className="text-foreground">Step 2 — Match & Email:</strong> model, fuel, mileage, year, and keywords refine those results. Email only when match score ≥ your minimum.
          </p>
          <p className="text-xs">Facebook also supports sort, date listed, year, mileage, and transmission in URL — we can add those to Step 1 later.</p>
          <ul className="space-y-2 list-disc pl-5">
            <li><strong className="text-foreground">Include Keywords</strong> — boosts match score when found in the listing.</li>
            <li><strong className="text-foreground">Exclude Keywords</strong> — listings with these words are skipped (e.g. Motorschaden, Defekt).</li>
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Monitoring loop
          </CardTitle>
          <CardDescription>What happens when you press Start</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="space-y-3 list-none p-0 m-0">
            <Step n={1}><strong className="text-foreground">Start</strong> → Marketplace → login (manual first time) → <code className="text-xs bg-muted px-1 py-0.5 rounded">/vehicles</code> → location once → price → scan matched listings</Step>
            <Step n={2}>Wait a random number of <strong className="text-foreground">seconds</strong> (min–max on <SectionLink to="/monitoring" icon={Activity} label="Monitoring" />)</Step>
            <Step n={3}><strong className="text-foreground">Reload /vehicles</strong> in the same Chrome window → price → scan again</Step>
            <Step n={4}>Repeat step 2 until you press <strong className="text-foreground">Stop</strong></Step>
          </ol>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Monitoring settings
          </CardTitle>
          <CardDescription>Start / Stop and check interval</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-muted-foreground">
          <div className="flex items-start gap-3 p-3 rounded-lg border border-border">
            <Play className="h-4 w-4 mt-0.5 shrink-0 text-emerald-600" />
            <div>
              <p className="font-medium text-foreground">Start / Stop (Dashboard header)</p>
              <p className="mt-1">Opens Chromium once, applies filters, then keeps checking listings until Stop. Same browser session is reused.</p>
            </div>
          </div>
          <p><strong className="text-foreground">Check interval</strong> — min and max <strong className="text-foreground">seconds</strong> on <SectionLink to="/monitoring" icon={Activity} label="Monitoring" />. After each pass (scroll + match), the bot waits a random time in that range, refreshes the Vehicles page, and looks for new listings.</p>
          <p><strong className="text-foreground">Listings saved</strong> — only vehicles that match <strong className="text-foreground">all</strong> your filter fields (brand, model, fuel, mileage, etc.). Price and location are applied on Facebook first.</p>
          <p><strong className="text-foreground">Headless mode</strong> — <SectionLink to="/settings" icon={Settings} label="Settings" /> → Browser. Turn off to see Chrome and log in manually the first time.</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="h-5 w-5" />
            Two Different Logins
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p><strong className="text-foreground">Admin login</strong> — for this dashboard only (filters, Start/Stop, settings). Set via <code className="text-xs bg-muted px-1 py-0.5 rounded">ADMIN_EMAIL</code> / <code className="text-xs bg-muted px-1 py-0.5 rounded">ADMIN_PASSWORD</code> in backend <code className="text-xs bg-muted px-1 py-0.5 rounded">.env</code>. Protects your control panel when deployed on a server.</p>
          <p><strong className="text-foreground">Facebook login</strong> — first time log in manually in the Chrome window (Headless off). Session is saved to <code className="text-xs bg-muted px-1 py-0.5 rounded">data/facebook_session.json</code> for later runs.</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mail className="h-5 w-5" />
            Email Alerts
          </CardTitle>
          <CardDescription>Where alerts are sent vs how they are sent</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p><strong className="text-foreground">Alert recipient</strong> — set in <SectionLink to="/settings" icon={Settings} label="Settings" />. This is the email address that receives vehicle notifications.</p>
          <p><strong className="text-foreground">SMTP sender</strong> — configured in the backend <code className="text-xs bg-muted px-1 py-0.5 rounded">.env</code> file only (Gmail host, sender email, app password). Not shown in the dashboard.</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Pages Overview</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li className="flex items-center gap-2"><LayoutDashboard className="h-4 w-4" /> <strong className="text-foreground">Dashboard</strong> — stats and charts; click cards for details</li>
            <li className="flex items-center gap-2"><Filter className="h-4 w-4" /> <strong className="text-foreground">Filters</strong> — create and manage search criteria</li>
            <li className="flex items-center gap-2"><Car className="h-4 w-4" /> <strong className="text-foreground">Listings</strong> — matched vehicles only</li>
            <li className="flex items-center gap-2"><Bell className="h-4 w-4" /> <strong className="text-foreground">Notifications</strong> — email alert history</li>
            <li className="flex items-center gap-2"><Activity className="h-4 w-4" /> <strong className="text-foreground">Monitoring</strong> — listing check interval (seconds)</li>
            <li className="flex items-center gap-2"><FileText className="h-4 w-4" /> <strong className="text-foreground">Logs</strong> — system activity and errors</li>
            <li className="flex items-center gap-2"><Settings className="h-4 w-4" /> <strong className="text-foreground">Settings</strong> — alert emails and password</li>
            <li className="flex items-center gap-2"><KeyRound className="h-4 w-4" /> <strong className="text-foreground">Help</strong> — this guide</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
