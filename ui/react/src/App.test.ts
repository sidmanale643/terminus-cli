import assert from "node:assert/strict";
import type { GuidedQuestion } from "./protocol.js";
import {
  buildQuestionAnswerSummary,
  calculateBannerRows,
  getQuestionAdvanceResult,
  markdownDisplayRows,
  questionActionLabel,
  shouldRenderWorkerSeparator,
  shouldUseQuestionReview,
  workerPaneHeights,
  workerSeparatorCount,
} from "./App.js";

const questions: GuidedQuestion[] = [
  {
    text: "Which files should I update?",
    options: ["Backend only", "Frontend only", "Both"],
    allowMultiple: false,
  },
  {
    text: "Which checks should I run?",
    options: ["Python tests", "React tests", "Typecheck"],
    allowMultiple: true,
  },
  {
    text: "How should I verify the UI?",
    options: ["Manual only", "Tests only", "Both"],
    allowMultiple: false,
  },
];

assert.equal(calculateBannerRows(100, true), 8);
assert.equal(calculateBannerRows(72, true), 4);
assert.equal(calculateBannerRows(100, false), 0);

assert.equal(shouldUseQuestionReview(questions), true);
assert.equal(shouldUseQuestionReview(questions.slice(0, 2)), true);
assert.equal(shouldUseQuestionReview(questions.slice(0, 1)), false);
assert.equal(questionActionLabel(0, questions.length, true), "Next question");
assert.equal(questionActionLabel(2, questions.length, true), "Review answers");
assert.equal(questionActionLabel(1, 2, true), "Review answers");

assert.deepEqual(
  getQuestionAdvanceResult({
    questionIndex: 0,
    questions,
    selectedOptions: [[], [], []],
    notes: ["", "", ""],
  }),
  { type: "next_question" },
);

assert.deepEqual(
  getQuestionAdvanceResult({
    questionIndex: 1,
    questions,
    selectedOptions: [[], [], []],
    notes: ["", "", ""],
  }),
  { type: "next_question" },
);

assert.deepEqual(
  getQuestionAdvanceResult({
    questionIndex: 2,
    questions,
    selectedOptions: [[], [], []],
    notes: ["", "", ""],
  }),
  { type: "enter_review" },
);

assert.deepEqual(
  getQuestionAdvanceResult({
    questionIndex: 0,
    questions,
    selectedOptions: [[], [], []],
    notes: ["", "", ""],
  }),
  { type: "next_question" },
);

const summary = buildQuestionAnswerSummary(
  questions,
  [[1], [1, 2], [2]],
  ["", "Run both", "Manual pass"],
);
assert.match(summary, /1\. Which files should I update\?/);
assert.match(summary, /Selected options: Frontend only/);
assert.match(summary, /Selected options: React tests, Typecheck/);
assert.match(summary, /Additional input: Manual pass/);

const submitResult = getQuestionAdvanceResult({
  questionIndex: 0,
  questions: questions.slice(0, 1),
  selectedOptions: [[]],
  notes: [""],
});
assert.equal(submitResult.type, "submit");
if (submitResult.type === "submit") {
  assert.match(submitResult.content, /Selected options: None selected/);
}

assert.deepEqual(workerPaneHeights(11, 3), [3, 3, 3]);
assert.deepEqual(workerPaneHeights(12, 3), [4, 3, 3]);
assert.deepEqual(workerPaneHeights(4, 1), [4]);
assert.deepEqual(workerPaneHeights(4, 3), [1, 1, 1]);
assert.deepEqual(workerPaneHeights(0, 3), [0, 0, 0]);
assert.equal(workerSeparatorCount(11, 3), 2);
assert.equal(workerSeparatorCount(4, 3), 1);
assert.equal(workerSeparatorCount(2, 3), 0);
assert.equal(shouldRenderWorkerSeparator(0, 2), true);
assert.equal(shouldRenderWorkerSeparator(1, 2), false);
assert.equal(shouldRenderWorkerSeparator(0, 1), false);
assert.equal(shouldRenderWorkerSeparator(1, 3, 1), false);

assert.deepEqual(
  markdownDisplayRows("| Name | Status |\n| --- | --- |\n| Alpha | Ready |\n| Beta | In progress |", 80),
  [
    "| Name  | Status      |",
    "| ----- | ----------- |",
    "| Alpha | Ready       |",
    "| Beta  | In progress |",
  ],
);

assert.deepEqual(
  markdownDisplayRows("## Results\nPlain text", 80),
  ["Results", "Plain text"],
);

assert.deepEqual(
  markdownDisplayRows("| Very long column | Other |\n| --- | --- |\n| abcdefghij | value |", 24),
  [
    "| Very lo… | Other |",
    "| -------- | ----- |",
    "| abcdefg… | value |",
  ],
);
