//
//  NewsViewModel.swift
//  SportsScores
//

import Foundation

@MainActor
class NewsViewModel: ObservableObject {
    @Published var articles: [NewsItem] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let apiService = ESPNAPIService.shared

    func fetchNews(for sport: Sport) async {
        isLoading = articles.isEmpty
        errorMessage = nil
        do {
            articles = try await apiService.fetchNews(for: sport)
        } catch {
            errorMessage = APIError.unavailable("news")
        }
        isLoading = false
    }

    func refresh(for sport: Sport) async {
        await fetchNews(for: sport)
    }
}
