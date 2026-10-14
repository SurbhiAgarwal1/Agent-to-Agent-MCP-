import "@testing-library/jest-dom";

// Clean up mocks after each test
afterEach(() => {
  sessionStorage.clear();
  localStorage.clear();
});
