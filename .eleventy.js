module.exports = function(eleventyConfig) {
  // Pass through static assets from project root to _site/
  eleventyConfig.addPassthroughCopy({ "images": "images" });
  eleventyConfig.addPassthroughCopy({ "audio": "audio" });
  eleventyConfig.addPassthroughCopy({ "attic": "attic" });

  return {
    dir: {
      input: "src",
      output: "_site",
      includes: "_includes"
    },
    htmlTemplateEngine: "njk",
    markdownTemplateEngine: "njk"
  };
};
