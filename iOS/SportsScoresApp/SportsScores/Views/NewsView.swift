//
//  NewsView.swift
//  SportsScores
//
//  Displays league headlines from the ESPN news endpoint.
//  Tapping an article opens it in the in-app Safari browser.
//

import SwiftUI
import UIKit
import SafariServices

struct NewsView: View {
    let sport: Sport
    @StateObject private var viewModel = NewsViewModel()

    var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressView("Loading news…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = viewModel.errorMessage, viewModel.articles.isEmpty {
                // A refresh that fails keeps what's showing, as the scores list does.
                errorState(message: error)
            } else if viewModel.articles.isEmpty {
                emptyState
            } else {
                articleList
            }
        }
        .task { await viewModel.fetchNews(for: sport) }
        .refreshable {
            await viewModel.refresh(for: sport)
            // With a list showing, nothing else would say so.
            if let error = viewModel.errorMessage, !viewModel.articles.isEmpty {
                UIAccessibility.post(notification: .announcement, argument: error)
            }
        }
    }

    // MARK: - List

    private var articleList: some View {
        List(viewModel.articles) { article in
            NewsRow(article: article)
                .listRowSeparator(.visible)
                .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
        }
        .listStyle(.plain)
    }

    // MARK: - States

    private func errorState(message: String) -> some View {
        ErrorStateView(message: message) { Task { await viewModel.fetchNews(for: sport) } }
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "newspaper")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("No news available")
                .font(.headline)
                .foregroundColor(.secondary)
        }
    }
}

// MARK: - News Row

struct NewsRow: View {
    let article: NewsItem
    @State private var showSafari = false

    var body: some View {
        Button {
            if article.articleURL != nil { showSafari = true }
        } label: {
            VStack(alignment: .leading, spacing: 6) {
                Text(article.headline)
                    .font(.headline)
                    .foregroundColor(.primary)
                    .multilineTextAlignment(.leading)
                    .lineLimit(3)

                if let desc = article.description, !desc.isEmpty {
                    Text(desc)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }

                HStack(spacing: 8) {
                    if let byline = article.byline {
                        Text(byline)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    if let pub = article.published {
                        Spacer()
                        Text(pub, style: .relative)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(article.headline)
        .accessibilityHint(article.articleURL != nil ? "Double tap to open article." : "")
        .sheet(isPresented: $showSafari) {
            if let url = article.articleURL {
                SafariView(url: url)
                    .ignoresSafeArea()
            }
        }
    }
}

// MARK: - Safari wrapper

struct SafariView: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> SFSafariViewController {
        SFSafariViewController(url: url)
    }

    func updateUIViewController(_ uiViewController: SFSafariViewController, context: Context) {}
}

#Preview {
    NavigationStack {
        NewsView(sport: .mlb)
            .navigationTitle("MLB News")
    }
}
