// VFL Extraction Script for Chrome DevTools MCP
(async () => {
  // Wait for page to load
  await new Promise(r => setTimeout(r, 3000));
  
  // Extract React/Vue state for VFL fixtures
  const extractFixtures = () => {
    try {
      // Try to find fixture data in the page state
      const state = window.__INITIAL_STATE__ || window.__PRELOADED_STATE__ || {};
      
      // Common selectors for VFL data
      const fixtureSelectors = [
        '.fixture-item', '.match-item', '.vfl-fixture',
        '[data-fixture]', '[data-match]'
      ];
      
      let fixtures = [];
      
      // Try DOM extraction
      document.querySelectorAll('.fixture-item').forEach((el, i) => {
        fixtures.push({
          home: el.querySelector('.home-team, .team-home')?.textContent?.trim(),
          away: el.querySelector('.away-team, .team-away')?.textContent?.trim(),
          oddsHome: el.querySelector('.odd-1, .odd-home')?.textContent?.trim(),
          oddsDraw: el.querySelector('.odd-x, .odd-draw')?.textContent?.trim(),
          oddsAway: el.querySelector('.odd-2, .odd-away')?.textContent?.trim()
        });
      });
      
      return fixtures.filter(f => f.home && f.away);
    } catch (e) {
      return { error: e.message };
    }
  };
  
  return extractFixtures();
})();
