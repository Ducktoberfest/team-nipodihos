import { useState } from "react";
import Logo from "./components/Logo.jsx";
import Landing from "./components/Landing.jsx";
import ReportForm from "./components/ReportForm.jsx";
import ReportList from "./components/ReportList.jsx";
import MatchesView from "./components/MatchesView.jsx";

const NAV = [
  { page: "home", label: "Home" },
  { page: "new", label: "Report an item" },
  { page: "list", label: "Browse reports" },
];

export default function App() {
  const [page, setPage] = useState("home");
  const [selectedReportId, setSelectedReportId] = useState(null);
  // True when we arrive from the report form: matching starts by itself.
  const [autoRunMatches, setAutoRunMatches] = useState(false);

  function openMatches(reportId, autoRun = false) {
    setSelectedReportId(reportId);
    setAutoRunMatches(autoRun);
    setPage("matches");
  }

  return (
    <>
      <header className="app-header">
        <div className="container">
          <button className="logo" onClick={() => setPage("home")}>
            <Logo />
            <span className="wordmark">
              Found<span>It</span>
            </span>
          </button>
          <nav className="app-nav">
            {NAV.map((item) => (
              <button
                key={item.page}
                className={`nav-link ${page === item.page ? "active" : ""}`}
                onClick={() => setPage(item.page)}
              >
                {item.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main>
        <div className="container">
          {page === "home" && <Landing />}

          {page === "new" && (
            <ReportForm onCreated={(report) => openMatches(report.id, true)} />
          )}

          {page === "list" && (
            <ReportList onOpenMatches={(id) => openMatches(id)} />
          )}

          {page === "matches" && selectedReportId != null && (
            <MatchesView
              reportId={selectedReportId}
              autoRun={autoRunMatches}
              onBack={() => setPage("list")}
            />
          )}
        </div>
      </main>

      <footer className="app-footer">
        <div className="container">
          FoundIt suggests; you verify. A suggestion is never proof of
          ownership — always confirm a private detail before handing an item
          over.
        </div>
      </footer>
    </>
  );
}
