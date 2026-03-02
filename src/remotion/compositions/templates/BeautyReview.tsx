import React from 'react';
import VideoTemplate, { VideoTemplateProps } from '../VideoTemplate';

export default function BeautyReview(props: VideoTemplateProps) {
  return (
    <VideoTemplate
      {...props}
      transition="fade"
      style={{
        ...props.style,
        primaryColor: '#FFB5C2',
        subtitleFontSize: 24,
        overlayOpacity: 0.4,
      }}
    />
  );
}
