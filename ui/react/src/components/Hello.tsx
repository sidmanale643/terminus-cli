import React from "react";
import { Box, Text } from "ink";
import { COLORS } from "../theme.js";

export const Hello = () => (
  <Box justifyContent="center">
    <Text color={COLORS.accent} bold>
      Hello Cutie
    </Text>
  </Box>
);
